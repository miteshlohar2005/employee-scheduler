import os

from fastapi.testclient import TestClient

from api.main import app
from db.connection import get_db


os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "test-admin-password"
client = TestClient(app)
login = client.post("/auth/login", json={"username": "admin", "password": "test-admin-password"})
assert login.status_code == 200
client.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})


def test_mutations_require_authentication():
    anonymous = TestClient(app)
    response = anonymous.post("/roster/generate", json={"year": 2026, "month": 6})
    assert response.status_code == 401


def test_publish_conflict_returns_structured_detail_and_keeps_draft():
    db = get_db()
    employee = db.roster_employees.find_one({"employee_id": "EMP001"}, {"_id": 0})
    if employee:
        leaves = set(employee.get("leaves", []))
        leaves.discard("2026-11-10")
        db.roster_employees.update_one(
            {"employee_id": "EMP001"},
            {"$set": {"leaves": sorted(leaves)}},
        )

    generated = client.post("/roster/generate", json={"year": 2026, "month": 11})
    assert generated.status_code == 200
    roster = generated.json()

    working_date = None
    employee_id = "EMP001"
    employee_process_id = "B1-CS"
    for day, assignments in roster["schedule"].items():
        if any(employee_id in employee_ids for employee_ids in assignments.values()):
            working_date = day
            break
    if working_date is None:
        working_date = "2026-11-10"

    changed = client.post(
        "/roster/2026/11/leave",
        json={"employee_id": employee_id, "date": working_date, "type": "leave"},
    )
    assert changed.status_code == 200

    validated = client.post("/roster/2026/11/validate")
    assert validated.status_code == 200

    published = client.post("/roster/2026/11/publish")
    assert published.status_code == 409
    detail = published.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["publish_status"] == "draft"
    assert detail["mandatory_conflict_count"] >= 1
    assert isinstance(detail["conflicts"], list)
    assert any(
        conflict["employee_id"] == employee_id
        for conflict in detail["conflicts"]
    )

    stored = client.get("/roster/2026/11")
    assert stored.status_code == 200
    assert stored.json()["publish_status"] == "draft"

    client.delete(
        "/roster/2026/11/leave",
        params={"employee_id": employee_id, "date": working_date, "type": "leave"},
    )


def test_roster_domain_and_month_generation():
    domain = client.get("/roster/domain")
    assert domain.status_code == 200
    body = domain.json()
    assert len(body["employees"]) >= 30
    assert len(body["brands"]) >= 10

    response = client.post("/roster/generate", json={"year": 2026, "month": 2})
    assert response.status_code == 200
    roster = response.json()
    assert roster["status"] == "FEASIBLE"
    assert roster["publish_status"] == "draft"
    assert roster["can_publish"] is True


def test_publish_requires_validation_and_rejects_draft():
    client.post("/roster/generate", json={"year": 2026, "month": 3})
    draft_response = client.post("/roster/2026/3/publish")
    assert draft_response.status_code == 409

    validated_response = client.post("/roster/2026/3/validate")
    assert validated_response.status_code == 200
    assert validated_response.json()["publish_status"] == "validated"

    published_response = client.post("/roster/2026/3/publish")
    assert published_response.status_code == 200
    assert published_response.json()["publish_status"] == "published"


def test_leave_change_invalidates_validation_and_detects_coverage():
    generated = client.post("/roster/generate", json={"year": 2026, "month": 1})
    assert generated.status_code == 200
    roster = generated.json()

    employee_id = None
    process_id = None
    working_date = None
    for day, assignments in roster["schedule"].items():
        for candidate_process, employee_ids in assignments.items():
            if employee_ids:
                employee_id = employee_ids[0]
                process_id = candidate_process
                working_date = day
                break
        if employee_id:
            break

    assert employee_id and process_id and working_date
    validated = client.post("/roster/2026/1/validate")
    assert validated.status_code == 200

    changed = client.post(
        "/roster/2026/1/leave",
        json={"employee_id": employee_id, "date": working_date, "type": "leave"},
    )
    assert changed.status_code == 200
    assert changed.json()["publish_status"] == "draft"
    assert any(
        conflict["employee_id"] == employee_id
        for conflict in changed.json()["conflicts"]
    )

    client.delete(
        "/roster/2026/1/leave",
        params={"employee_id": employee_id, "date": working_date, "type": "leave"},
    )


def test_crud_employee_brand_assignment_and_holiday():
    db = get_db()
    db.roster_employees.delete_many({"employee_id": "EMPTEST"})
    db.roster_brands.delete_many({"brand_id": "BTEST"})
    db.roster_processes.delete_many({"process_id": "BTEST-CS"})
    db.roster_holidays.delete_many({"date": "2026-12-31"})

    pod = client.get("/roster/domain").json()["pods"][0]["pod_id"]
    employee = client.post(
        "/management/employees",
        json={
            "employee_id": "EMPTEST",
            "name": "Test Operator",
            "pod_id": pod,
            "employment_type": "full_time",
            "weekly_off": 6,
        },
    )
    assert employee.status_code == 200

    employee_update = client.put(
        "/management/employees/EMPTEST",
        json={"name": "Updated Operator", "weekly_off": 5, "leaves": ["2026-12-31"]},
    )
    assert employee_update.status_code == 200
    assert employee_update.json()["name"] == "Updated Operator"

    brand = client.post("/management/brands", json={"brand_id": "BTEST", "name": "Test Brand"})
    assert brand.status_code == 200
    process = client.post(
        "/management/processes",
        json={
            "process_id": "BTEST-CS",
            "brand_id": "BTEST",
            "name": "Customer Support",
            "calendar": "365",
            "minimum_staff": 1,
        },
    )
    assert process.status_code == 200
    assignment = client.post(
        "/management/assignments",
        json={"employee_id": "EMPTEST", "brand_id": "BTEST", "process_id": "BTEST-CS"},
    )
    assert assignment.status_code == 200
    assignment_delete = client.delete(
        "/management/assignments",
        params={
            "employee_id": "EMPTEST",
            "brand_id": "BTEST",
            "process_id": "BTEST-CS",
        },
    )
    assert assignment_delete.status_code == 200

    holiday = client.post(
        "/management/holidays",
        json={"date": "2026-12-31", "name": "Test Holiday", "scope": "India"},
    )
    assert holiday.status_code == 200
    assert client.delete("/management/holidays/2026-12-31").status_code == 200

    assert client.delete("/management/processes/BTEST-CS").status_code == 200
    assert client.delete("/management/brands/BTEST").status_code == 200
    assert client.delete("/management/employees/EMPTEST").status_code == 200


def test_roster_entry_edit_revalidates_and_existing_weekly_api_works():
    client.post("/roster/generate", json={"year": 2026, "month": 5})
    domain = client.get("/roster/domain").json()
    employee = domain["employees"][0]
    process = domain["processes"][0]

    edited = client.put(
        "/roster/2026/5/entry",
        json={
            "employee_id": employee["employee_id"],
            "process_id": process["process_id"],
            "date": "2026-05-01",
            "action": "remove",
        },
    )
    assert edited.status_code == 200
    assert edited.json()["publish_status"] == "draft"

    stores = client.get("/stores")
    assert stores.status_code == 200
    assert len(stores.json()) >= 1
