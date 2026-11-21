import calendar

from db.roster_seed import build_seed_data
from scheduler.monthly_roster import (
    generate_monthly_roster,
    process_operates,
    validate_monthly_roster,
)


def test_sample_dataset_has_30_employees_and_80_percent_single_resource_brands():
    domain = build_seed_data()
    assert len(domain["employees"]) >= 30
    assert len(domain["brands"]) == 30

    employee_ids_by_brand = {}
    for assignment in domain["assignments"]:
        employee_ids_by_brand.setdefault(assignment["brand_id"], set()).add(
            assignment["employee_id"]
        )
    single_resource = sum(
        1 for employee_ids in employee_ids_by_brand.values() if len(employee_ids) == 1
    )
    ratio = single_resource / len(domain["brands"])
    assert ratio == 0.8


def test_monthly_roster_generation_is_feasible_and_has_coverage():
    domain = build_seed_data()
    result = generate_monthly_roster(domain, 2026, 1)
    assert result["status"] == "FEASIBLE"
    assert result["can_publish"] is True
    assert result["publish_status"] == "draft"
    assert result["conflicts"] == []

    for day_coverage in result["coverage"].values():
        for coverage in day_coverage.values():
            if coverage["status"] != "CLOSED":
                assert coverage["actual"] >= coverage["required"]


def test_leave_change_revalidation_detects_unavailability_conflict():
    domain = build_seed_data()
    employee = domain["employees"][0]
    employee["leaves"] = ["2026-01-05"]
    result = generate_monthly_roster(domain, 2026, 1)

    schedule = result["schedule"]
    validation = validate_monthly_roster(domain, 2026, 1, schedule)
    assert validation["status"] in {"FEASIBLE", "INFEASIBLE"}

    process_id = next(
        assignment["process_id"]
        for assignment in domain["assignments"]
        if assignment["employee_id"] == employee["employee_id"]
    )
    for day in schedule:
        if employee["employee_id"] in schedule[day].get(process_id, []):
            break
    else:
        return

    employee["leaves"] = [day]
    validation = validate_monthly_roster(domain, 2026, 1, schedule)
    assert validation["can_publish"] is False
    assert any(conflict["type"] == "leave_conflict" for conflict in validation["conflicts"])


def test_impossible_coverage_returns_explanations_not_a_valid_roster():
    domain = build_seed_data()
    domain["processes"] = [
        process for process in domain["processes"]
        if process["process_id"] != "B1-CS"
    ]
    domain["assignments"] = [
        assignment for assignment in domain["assignments"]
        if assignment["process_id"] != "B1-CS"
    ]
    domain["processes"].append({
        "process_id": "B1-CS",
        "brand_id": "B1",
        "name": "Customer Support",
        "calendar": "365",
        "minimum_staff": 1,
        "active": True,
    })

    result = generate_monthly_roster(domain, 2026, 1)
    assert result["status"] == "INFEASIBLE"
    assert result["can_publish"] is False
    assert result["conflicts"]
    assert result["conflicts"][0]["type"] == "uncovered_process"


def test_single_resource_brand_unavailability_creates_actionable_gap():
    domain = build_seed_data()
    result = generate_monthly_roster(domain, 2026, 1)
    assert result["status"] == "FEASIBLE"

    employee_id = next(
        assignment["employee_id"]
        for assignment in domain["assignments"]
        if assignment["brand_id"] == "B1"
    )
    employee = next(item for item in domain["employees"] if item["employee_id"] == employee_id)
    working_day = next(
        day
        for day, assignments in result["schedule"].items()
        if any(employee_id in ids for ids in assignments.values())
    )
    employee["leaves"] = [working_day]

    validation = validate_monthly_roster(domain, 2026, 1, result["schedule"])
    assert validation["status"] == "INFEASIBLE"
    affected = [
        conflict for conflict in validation["conflicts"]
        if conflict["employee_id"] == employee_id
        and conflict["date"] == working_day
    ]
    assert affected
    assert all(conflict["resolution"] for conflict in affected)
    assert any(conflict["process_id"].startswith("B1-") for conflict in affected)


def test_calendar_rules_and_cross_brand_overlap_are_distinct():
    from datetime import date

    holidays = {"2026-01-26"}
    processes = [
        {"process_id": "P365", "brand_id": "B1", "calendar": "365", "minimum_staff": 1},
        {"process_id": "PWEEK", "brand_id": "B2", "calendar": "weekdays", "minimum_staff": 1},
        {"process_id": "POFF", "brand_id": "B3", "calendar": "sunday_holiday_off", "minimum_staff": 1},
    ]
    assert process_operates(processes[0], date(2026, 1, 26), holidays)
    assert not process_operates(processes[1], date(2026, 1, 26), holidays)
    assert not process_operates(processes[2], date(2026, 1, 25), holidays)


def test_multiple_months_generate_and_revalidate():
    domain = build_seed_data()
    for year, month in [(2026, 2), (2026, 10), (2026, 12)]:
        result = generate_monthly_roster(domain, year, month)
        assert result["status"] in {"FEASIBLE", "INFEASIBLE"}
        if result["status"] == "FEASIBLE":
            assert len(result["schedule"]) == calendar.monthrange(year, month)[1]
            validation = validate_monthly_roster(
                domain,
                year,
                month,
                result["schedule"],
            )
            assert validation["can_publish"] is True
        else:
            assert result["can_publish"] is False
            assert result["conflicts"]
