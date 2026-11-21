"""FastAPI backend layer for the employee scheduler.

Exposes the existing Excel import and CP-SAT scheduling logic over HTTP so
the React frontend (frontend/) can call it directly. MongoDB remains the
backend's internal working store; Excel uploads are now processed on
demand via POST /upload, rather than only being read from the fixed
data/preset_data.xlsx preset file.
"""

import io
from datetime import date
import os

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi import Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db.connection import get_db
from db.excel_import import import_stores_and_employees
from scheduler.generate_schedule import generate_weekly_schedule
from scheduler.peak_hours import detect_peak_window, is_peak_hour
from scheduler.staffing_rules import (
    get_eligible_employees,
    get_required_staffing,
    get_weekly_budget_range,
)
from db.roster_repositories import get_month_roster, get_roster_domain, save_month_roster
from db.roster_seed import seed_roster_data
from scheduler.monthly_roster import generate_monthly_roster, validate_monthly_roster
from api.security import login, logout, require_bearer

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

app = FastAPI(title="Employee Scheduler API")

# Permissive for local dev only, so a React dev server on a different port
# (e.g. Vite's 5173) can call this API. Tighten before any real deployment.
cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.post("/auth/login")
def auth_login(payload: dict = Body(...)):
    token = login(payload.get("username"), payload.get("password"))
    return {"access_token": token, "token_type": "bearer"}


@app.post("/auth/logout")
def auth_logout(request: Request):
    authorization = request.headers.get("authorization", "")
    token = authorization.split(" ", 1)[1].strip() if authorization.lower().startswith("bearer ") else None
    logout(token)
    return {"logged_out": True}


@app.get("/auth/status")
def auth_status(request: Request):
    try:
        require_bearer(request)
        return {"authenticated": True}
    except HTTPException:
        return {"authenticated": False}


@app.middleware("http")
async def require_auth_for_mutations(request: Request, call_next):
    if request.method in {"POST", "PUT", "DELETE"}:
        if request.url.path not in {"/auth/login", "/auth/logout"}:
            try:
                require_bearer(request)
            except HTTPException as exc:
                origin = request.headers.get("origin")
                cors_headers = (
                    {"Access-Control-Allow-Origin": origin}
                    if origin in cors_origins
                    else {}
                )
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers={
                        "WWW-Authenticate": "Bearer",
                        **cors_headers,
                    },
                )
    return await call_next(request)


def _hour_label(hour):
    """Format a 24-hour value like 14 as a label like "2pm"."""
    if hour == 12:
        return "12pm"
    if hour > 12:
        return f"{hour - 12}pm"
    return f"{hour}am"


def _build_eligible_employees_payload(eligible_employees, result):
    """Return the eligible roster with each employee's actual hours this week."""
    scheduled_hours_by_employee = {}
    if result["status"] == "FEASIBLE":
        for day_assignments in result["schedule"].values():
            for employee_id, info in day_assignments.items():
                scheduled_hours_by_employee[employee_id] = scheduled_hours_by_employee.get(
                    employee_id, 0
                ) + len(info["hours"])

    payload = []
    for employee in eligible_employees:
        payload.append(
            {
                "employee_id": employee["employee_id"],
                "name": employee["name"],
                "employment_type": employee["employment_type"],
                "scheduled_hours": scheduled_hours_by_employee.get(employee["employee_id"], 0),
            }
        )
    payload.sort(key=lambda employee: employee["name"])
    return payload


def _insert_into_mongo(stores, employees):
    db = get_db()
    db.stores.delete_many({})
    db.employees.delete_many({})
    db.stores.insert_many(stores)
    db.employees.insert_many(employees)


@app.post("/upload")
async def upload_excel(file: UploadFile = File(...)):
    """Import an uploaded Excel workbook (Stores/Employees/Hourly_Sales
    sheets) and load it into MongoDB, replacing any previous data."""
    contents = await file.read()

    try:
        stores, employees = import_stores_and_employees(io.BytesIO(contents))
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={
                "stores_imported": 0,
                "employees_imported": 0,
                "errors": [str(exc)],
            },
        )

    _insert_into_mongo(stores, employees)

    return {
        "stores_imported": len(stores),
        "employees_imported": len(employees),
        "errors": [],
    }


@app.get("/stores")
def list_stores():
    """Return stores currently in MongoDB, for a store-selector dropdown."""
    db = get_db()
    stores = db.stores.find(
        {}, {"_id": 0, "store_id": 1, "brand": 1, "branch": 1, "size_tier": 1}
    )
    return list(stores)


@app.get("/schedule/{store_id}")
def get_schedule(store_id: str):
    """Run the weekly CP-SAT schedule for one store and return it as JSON."""
    db = get_db()
    store = db.stores.find_one({"store_id": store_id}, {"_id": 0})
    if store is None:
        raise HTTPException(status_code=404, detail=f"Store {store_id!r} not found")

    employees = list(db.employees.find({}, {"_id": 0}))
    eligible_employees = get_eligible_employees(employees, store["branch"])

    try:
        result = generate_weekly_schedule(store, eligible_employees)
        peak_window = detect_peak_window(store["hourly_sales"])
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Store {store_id!r} has no hourly sales data - check that "
                "Store_Code matches between the Stores and Hourly_Sales "
                "sheets in your upload."
            ),
        ) from exc

    budget_min, budget_max = get_weekly_budget_range(store)

    response = {
        "store_id": store_id,
        "status": result["status"],
        "eligible_employees": _build_eligible_employees_payload(eligible_employees, result),
        "peak_window": {
            "start_hour": peak_window["start_hour"],
            "end_hour": peak_window["end_hour"],
            "hours": peak_window["hours"],
            "start_label": _hour_label(peak_window["start_hour"]),
            "end_label": _hour_label(peak_window["end_hour"] + 1),
        },
        "weekly_budget_range": {"min": budget_min, "max": budget_max},
    }

    if result["status"] != "FEASIBLE":
        response["message"] = (
            "No feasible schedule could be found for this store with its "
            "current eligible employees."
        )
        return response

    response["required_staffing_per_hour"] = [
        {
            "hour": hour,
            "label": _hour_label(hour),
            "is_peak": is_peak_hour(hour, peak_window),
            "required_staffing": get_required_staffing(
                store, is_peak_hour(hour, peak_window)
            ),
        }
        for hour in result["hours"]
    ]
    response["total_weekly_hours"] = result["total_weekly_hours"]

    schedule_by_day = {}
    for day_index, day_name in enumerate(DAY_NAMES):
        assignments = result["schedule"][day_index]
        schedule_by_day[day_name] = [
            {
                "employee_id": employee_id,
                "name": info["name"],
                "employment_type": info["employment_type"],
                "hours": info["hours"],
                "start_label": _hour_label(info["hours"][0]),
                "end_label": _hour_label(info["hours"][-1] + 1),
            }
            for employee_id, info in assignments.items()
        ]
    response["schedule"] = schedule_by_day

    return response


def _ensure_roster_data():
    domain = get_roster_domain()
    if not domain["brands"] or not domain["employees"]:
        seed_roster_data()
        domain = get_roster_domain()
    return domain


@app.get("/roster/domain")
def list_roster_domain():
    """Return configured pods, brands, processes, employees, assignments, and holidays."""
    return _ensure_roster_data()


@app.post("/roster/generate")
def generate_roster(payload: dict = Body(...)):
    """Generate a draft monthly roster; infeasible drafts are never publishable."""
    year = payload.get("year")
    month = payload.get("month")
    if not isinstance(year, int) or not isinstance(month, int):
        raise HTTPException(status_code=422, detail="year and month must be integers")
    if not 2000 <= year <= 2100 or month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="year must be 2000-2100 and month 1-12")
    domain = _ensure_roster_data()
    result = generate_monthly_roster(domain, year, month)
    save_month_roster(result)
    return result


@app.get("/roster/{year}/{month}")
def get_roster(year: int, month: int):
    result = get_month_roster(year, month)
    if result is None:
        raise HTTPException(status_code=404, detail="No monthly roster has been generated")
    return result


@app.post("/roster/{year}/{month}/publish")
def publish_roster(year: int, month: int):
    result = get_month_roster(year, month)
    if result is None:
        raise HTTPException(status_code=404, detail="No monthly roster has been generated")
    conflicts = result.get("conflicts", [])
    mandatory_conflicts = [
        conflict for conflict in conflicts
        if conflict.get("constraint") == "mandatory"
        or conflict.get("severity") == "critical"
    ]
    if result.get("status") != "FEASIBLE" or not result.get("can_publish") or mandatory_conflicts:
        if result.get("publish_status") != "draft":
            result["publish_status"] = "draft"
            save_month_roster(result)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Cannot publish a roster with unresolved mandatory conflicts.",
                "publish_status": "draft",
                "mandatory_conflict_count": len(mandatory_conflicts),
                "conflicts": mandatory_conflicts,
            },
        )
    if result.get("publish_status") != "validated":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Roster must be validated before publishing.",
                "publish_status": "draft",
                "mandatory_conflict_count": 0,
                "conflicts": [],
            },
        )
    domain = _ensure_roster_data()
    validation = validate_monthly_roster(
        domain, year, month, result.get("schedule", {})
    )
    if validation["status"] != "FEASIBLE":
        result["status"] = "INFEASIBLE"
        result["can_publish"] = False
        result["conflicts"] = validation["conflicts"]
        result["publish_status"] = "draft"
        save_month_roster(result)
        raise HTTPException(status_code=409, detail=validation)

    result["publish_status"] = "published"
    result["can_publish"] = True
    save_month_roster(result)
    return result


@app.post("/roster/{year}/{month}/leave")
def change_employee_leave(year: int, month: int, payload: dict = Body(...)):
    """Approve a leave or comp-off and revalidate the generated monthly roster."""
    employee_id = payload.get("employee_id")
    leave_date = payload.get("date")
    leave_type = payload.get("type", "leave")
    if not employee_id or not leave_date:
        raise HTTPException(status_code=422, detail="employee_id and date are required")
    try:
        leave_day = date.fromisoformat(leave_date)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="date must use YYYY-MM-DD")
    if leave_day.year != year or leave_day.month != month:
        raise HTTPException(status_code=422, detail="date is outside the selected roster month")
    if leave_type not in {"leave", "comp_off", "availability"}:
        raise HTTPException(status_code=422, detail="type must be leave, comp_off, or availability")

    db = get_db()
    employee = db.roster_employees.find_one({"employee_id": employee_id}, {"_id": 0})
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    field = {
        "leave": "leaves",
        "comp_off": "comp_offs",
        "availability": "availability",
    }[leave_type]
    values = set(employee.get(field, []))
    values.add(leave_date)
    db.roster_employees.update_one(
        {"employee_id": employee_id},
        {"$set": {field: sorted(values)}},
    )

    result = get_month_roster(year, month)
    if result is None:
        raise HTTPException(status_code=404, detail="No monthly roster has been generated")
    domain = _ensure_roster_data()
    validation = validate_monthly_roster(
        domain, year, month, result.get("schedule", {})
    )
    result["status"] = validation["status"]
    result["can_publish"] = validation["can_publish"]
    result["publish_status"] = "draft"
    result["conflicts"] = validation["conflicts"]
    result["message"] = validation["message"]
    save_month_roster(result)
    return result


@app.delete("/roster/{year}/{month}/leave")
def remove_employee_leave(
    year: int,
    month: int,
    employee_id: str,
    date: str,
    type: str,
):
    if type not in {"leave", "comp_off", "availability"}:
        raise HTTPException(status_code=422, detail="type must be leave, comp_off, or availability")
    db = get_db()
    employee = db.roster_employees.find_one({"employee_id": employee_id}, {"_id": 0})
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    field = {"leave": "leaves", "comp_off": "comp_offs", "availability": "availability"}[type]
    values = set(employee.get(field, []))
    values.discard(date)
    db.roster_employees.update_one(
        {"employee_id": employee_id},
        {"$set": {field: sorted(values)}},
    )
    roster = get_month_roster(year, month)
    if roster is None:
        raise HTTPException(status_code=404, detail="No monthly roster has been generated")
    domain = _ensure_roster_data()
    validation = validate_monthly_roster(domain, year, month, roster.get("schedule", {}))
    return _invalidate_and_save(roster, validation)


def _collection_document(collection_name, key, value):
    document = get_db()[collection_name].find_one({key: value}, {"_id": 0})
    if document is None:
        raise HTTPException(status_code=404, detail=f"{key} {value!r} not found")
    return document


def _required(payload, fields):
    missing = [field for field in fields if payload.get(field) in (None, "")]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required fields: {', '.join(missing)}",
        )


@app.post("/management/employees")
def create_employee(payload: dict = Body(...)):
    _required(payload, ["employee_id", "name", "pod_id"])
    db = get_db()
    if db.roster_employees.find_one({"employee_id": payload["employee_id"]}):
        raise HTTPException(status_code=409, detail="Employee ID already exists")
    if not db.roster_pods.find_one({"pod_id": payload["pod_id"]}):
        raise HTTPException(status_code=422, detail="Unknown pod_id")
    if payload.get("employment_type", "full_time") not in {"full_time", "part_time"}:
        raise HTTPException(status_code=422, detail="employment_type must be full_time or part_time")
    document = {
        "employee_id": payload["employee_id"],
        "name": payload["name"],
        "pod_id": payload["pod_id"],
        "employment_type": payload.get("employment_type", "full_time"),
        "weekly_off": int(payload.get("weekly_off", 6)),
        "availability": payload.get("availability", []),
        "leaves": payload.get("leaves", []),
        "comp_offs": payload.get("comp_offs", []),
        "preferences": payload.get("preferences", {}),
        "active": payload.get("active", True),
    }
    if document["weekly_off"] < 0 or document["weekly_off"] > 6:
        raise HTTPException(status_code=422, detail="weekly_off must be from 0 to 6")
    db.roster_employees.insert_one(document)
    document.pop("_id", None)
    return document


@app.put("/management/employees/{employee_id}")
def update_employee(employee_id: str, payload: dict = Body(...)):
    db = get_db()
    existing = db.roster_employees.find_one({"employee_id": employee_id}, {"_id": 0})
    if existing is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    if "pod_id" in payload and not db.roster_pods.find_one({"pod_id": payload["pod_id"]}):
        raise HTTPException(status_code=422, detail="Unknown pod_id")
    if "weekly_off" in payload and not 0 <= int(payload["weekly_off"]) <= 6:
        raise HTTPException(status_code=422, detail="weekly_off must be from 0 to 6")
    allowed = {
        "name", "pod_id", "employment_type", "weekly_off", "availability",
        "leaves", "comp_offs", "preferences", "active",
    }
    updates = {key: value for key, value in payload.items() if key in allowed}
    if "employment_type" in updates and updates["employment_type"] not in {"full_time", "part_time"}:
        raise HTTPException(status_code=422, detail="employment_type must be full_time or part_time")
    if updates:
        db.roster_employees.update_one({"employee_id": employee_id}, {"$set": updates})
    return db.roster_employees.find_one({"employee_id": employee_id}, {"_id": 0})


@app.delete("/management/employees/{employee_id}")
def delete_employee(employee_id: str):
    db = get_db()
    if db.roster_employees.find_one({"employee_id": employee_id}) is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    db.roster_employees.delete_one({"employee_id": employee_id})
    db.roster_assignments.delete_many({"employee_id": employee_id})
    db.roster_pods.update_many({"lead_employee_id": employee_id}, {"$set": {"lead_employee_id": None}})
    return {"deleted": True, "employee_id": employee_id}


@app.post("/management/brands")
def create_brand(payload: dict = Body(...)):
    _required(payload, ["brand_id", "name"])
    db = get_db()
    if db.roster_brands.find_one({"brand_id": payload["brand_id"]}):
        raise HTTPException(status_code=409, detail="Brand ID already exists")
    document = {"brand_id": payload["brand_id"], "name": payload["name"], "active": payload.get("active", True)}
    db.roster_brands.insert_one(document)
    document.pop("_id", None)
    return document


@app.put("/management/brands/{brand_id}")
def update_brand(brand_id: str, payload: dict = Body(...)):
    db = get_db()
    if db.roster_brands.find_one({"brand_id": brand_id}) is None:
        raise HTTPException(status_code=404, detail="Brand not found")
    allowed = {key: value for key, value in payload.items() if key in {"name", "active"}}
    if allowed:
        db.roster_brands.update_one({"brand_id": brand_id}, {"$set": allowed})
    return db.roster_brands.find_one({"brand_id": brand_id}, {"_id": 0})


@app.delete("/management/brands/{brand_id}")
def delete_brand(brand_id: str):
    db = get_db()
    if db.roster_brands.find_one({"brand_id": brand_id}) is None:
        raise HTTPException(status_code=404, detail="Brand not found")
    process_ids = [item["process_id"] for item in db.roster_processes.find({"brand_id": brand_id})]
    db.roster_brands.delete_one({"brand_id": brand_id})
    db.roster_processes.delete_many({"brand_id": brand_id})
    db.roster_assignments.delete_many({"brand_id": brand_id})
    return {"deleted": True, "brand_id": brand_id, "deleted_process_ids": process_ids}


@app.post("/management/processes")
def create_process(payload: dict = Body(...)):
    _required(payload, ["process_id", "brand_id", "name", "calendar"])
    db = get_db()
    if db.roster_processes.find_one({"process_id": payload["process_id"]}):
        raise HTTPException(status_code=409, detail="Process ID already exists")
    if not db.roster_brands.find_one({"brand_id": payload["brand_id"]}):
        raise HTTPException(status_code=422, detail="Unknown brand_id")
    if payload["calendar"] not in {"365", "weekdays", "sunday_holiday_off"}:
        raise HTTPException(status_code=422, detail="Unknown operating calendar")
    minimum_staff = int(payload.get("minimum_staff", 1))
    if minimum_staff < 1:
        raise HTTPException(status_code=422, detail="minimum_staff must be at least 1")
    document = {
        "process_id": payload["process_id"],
        "brand_id": payload["brand_id"],
        "name": payload["name"],
        "calendar": payload["calendar"],
        "minimum_staff": minimum_staff,
        "active": payload.get("active", True),
    }
    db.roster_processes.insert_one(document)
    document.pop("_id", None)
    return document


@app.put("/management/processes/{process_id}")
def update_process(process_id: str, payload: dict = Body(...)):
    db = get_db()
    if db.roster_processes.find_one({"process_id": process_id}) is None:
        raise HTTPException(status_code=404, detail="Process not found")
    if "brand_id" in payload and not db.roster_brands.find_one({"brand_id": payload["brand_id"]}):
        raise HTTPException(status_code=422, detail="Unknown brand_id")
    if "calendar" in payload and payload["calendar"] not in {"365", "weekdays", "sunday_holiday_off"}:
        raise HTTPException(status_code=422, detail="Unknown operating calendar")
    if "minimum_staff" in payload and int(payload["minimum_staff"]) < 1:
        raise HTTPException(status_code=422, detail="minimum_staff must be at least 1")
    allowed = {key: value for key, value in payload.items() if key in {"brand_id", "name", "calendar", "minimum_staff", "active"}}
    if allowed:
        db.roster_processes.update_one({"process_id": process_id}, {"$set": allowed})
    return db.roster_processes.find_one({"process_id": process_id}, {"_id": 0})


@app.delete("/management/processes/{process_id}")
def delete_process(process_id: str):
    db = get_db()
    if db.roster_processes.find_one({"process_id": process_id}) is None:
        raise HTTPException(status_code=404, detail="Process not found")
    db.roster_processes.delete_one({"process_id": process_id})
    db.roster_assignments.delete_many({"process_id": process_id})
    return {"deleted": True, "process_id": process_id}


@app.post("/management/pods")
def create_pod(payload: dict = Body(...)):
    _required(payload, ["pod_id", "name"])
    db = get_db()
    if db.roster_pods.find_one({"pod_id": payload["pod_id"]}):
        raise HTTPException(status_code=409, detail="Pod ID already exists")
    lead = payload.get("lead_employee_id")
    if lead and not db.roster_employees.find_one({"employee_id": lead}):
        raise HTTPException(status_code=422, detail="Unknown lead_employee_id")
    document = {"pod_id": payload["pod_id"], "name": payload["name"], "lead_employee_id": lead}
    db.roster_pods.insert_one(document)
    document.pop("_id", None)
    return document


@app.put("/management/pods/{pod_id}")
def update_pod(pod_id: str, payload: dict = Body(...)):
    db = get_db()
    if db.roster_pods.find_one({"pod_id": pod_id}) is None:
        raise HTTPException(status_code=404, detail="Pod not found")
    if "lead_employee_id" in payload and payload["lead_employee_id"]:
        if not db.roster_employees.find_one({"employee_id": payload["lead_employee_id"]}):
            raise HTTPException(status_code=422, detail="Unknown lead_employee_id")
    allowed = {key: value for key, value in payload.items() if key in {"name", "lead_employee_id"}}
    if allowed:
        db.roster_pods.update_one({"pod_id": pod_id}, {"$set": allowed})
    return db.roster_pods.find_one({"pod_id": pod_id}, {"_id": 0})


@app.delete("/management/pods/{pod_id}")
def delete_pod(pod_id: str):
    db = get_db()
    if db.roster_pods.find_one({"pod_id": pod_id}) is None:
        raise HTTPException(status_code=404, detail="Pod not found")
    employee_count = db.roster_employees.count_documents({"pod_id": pod_id})
    if employee_count:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete pod: {employee_count} employee(s) are assigned to it",
        )
    db.roster_pods.delete_one({"pod_id": pod_id})
    return {"deleted": True, "pod_id": pod_id}


@app.post("/management/assignments")
def create_assignment(payload: dict = Body(...)):
    _required(payload, ["employee_id", "brand_id", "process_id"])
    db = get_db()
    if not db.roster_employees.find_one({"employee_id": payload["employee_id"]}):
        raise HTTPException(status_code=422, detail="Unknown employee_id")
    if not db.roster_brands.find_one({"brand_id": payload["brand_id"]}):
        raise HTTPException(status_code=422, detail="Unknown brand_id")
    process = db.roster_processes.find_one({"process_id": payload["process_id"]}, {"_id": 0})
    if process is None:
        raise HTTPException(status_code=422, detail="Unknown process_id")
    if process["brand_id"] != payload["brand_id"]:
        raise HTTPException(status_code=422, detail="Process does not belong to brand")
    document = {
        "employee_id": payload["employee_id"],
        "brand_id": payload["brand_id"],
        "process_id": payload["process_id"],
        "active": payload.get("active", True),
    }
    if db.roster_assignments.find_one({key: document[key] for key in ("employee_id", "brand_id", "process_id")}):
        raise HTTPException(status_code=409, detail="Assignment already exists")
    db.roster_assignments.insert_one(document)
    document.pop("_id", None)
    return document


@app.put("/management/assignments")
def update_assignment(payload: dict = Body(...)):
    _required(payload, ["employee_id", "brand_id", "process_id"])
    db = get_db()
    query = {
        "employee_id": payload["employee_id"],
        "brand_id": payload["brand_id"],
        "process_id": payload["process_id"],
    }
    if db.roster_assignments.find_one(query) is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    process = db.roster_processes.find_one({"process_id": payload["process_id"]}, {"_id": 0})
    if process is None:
        raise HTTPException(status_code=404, detail="Process not found")
    if process["brand_id"] != payload["brand_id"]:
        raise HTTPException(status_code=422, detail="Process does not belong to brand")
    updates = {key: value for key, value in payload.items() if key in {"active"}}
    if updates:
        db.roster_assignments.update_one(query, {"$set": updates})
    return db.roster_assignments.find_one(query, {"_id": 0})


@app.delete("/management/assignments")
def delete_assignment(employee_id: str, brand_id: str, process_id: str):
    db = get_db()
    result = db.roster_assignments.delete_one({
        "employee_id": employee_id,
        "brand_id": brand_id,
        "process_id": process_id,
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return {"deleted": True, "employee_id": employee_id, "brand_id": brand_id, "process_id": process_id}


@app.post("/management/holidays")
def create_holiday(payload: dict = Body(...)):
    _required(payload, ["date", "name"])
    db = get_db()
    try:
        date.fromisoformat(payload["date"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="date must use YYYY-MM-DD")
    if db.roster_holidays.find_one({"date": payload["date"]}):
        raise HTTPException(status_code=409, detail="Holiday already exists")
    document = {"date": payload["date"], "name": payload["name"], "scope": payload.get("scope", "India")}
    db.roster_holidays.insert_one(document)
    document.pop("_id", None)
    return document


@app.put("/management/holidays/{holiday_date}")
def update_holiday(holiday_date: str, payload: dict = Body(...)):
    db = get_db()
    if db.roster_holidays.find_one({"date": holiday_date}) is None:
        raise HTTPException(status_code=404, detail="Holiday not found")
    allowed = {key: value for key, value in payload.items() if key in {"name", "scope"}}
    if allowed:
        db.roster_holidays.update_one({"date": holiday_date}, {"$set": allowed})
    return db.roster_holidays.find_one({"date": holiday_date}, {"_id": 0})


@app.delete("/management/holidays/{holiday_date}")
def delete_holiday(holiday_date: str):
    db = get_db()
    result = db.roster_holidays.delete_one({"date": holiday_date})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return {"deleted": True, "date": holiday_date}


def _invalidate_and_save(roster, validation):
    roster["status"] = validation["status"]
    roster["can_publish"] = validation["can_publish"]
    roster["publish_status"] = "draft"
    roster["conflicts"] = validation["conflicts"]
    roster["message"] = validation["message"]
    save_month_roster(roster)
    return roster


@app.post("/roster/{year}/{month}/validate")
def revalidate_roster(year: int, month: int):
    roster = get_month_roster(year, month)
    if roster is None:
        raise HTTPException(status_code=404, detail="No monthly roster has been generated")
    domain = _ensure_roster_domain()
    validation = validate_monthly_roster(domain, year, month, roster.get("schedule", {}))
    result = _invalidate_and_save(roster, validation)
    if validation["status"] == "FEASIBLE":
        result["publish_status"] = "validated"
        save_month_roster(result)
    return result


@app.put("/roster/{year}/{month}/entry")
def edit_roster_entry(year: int, month: int, payload: dict = Body(...)):
    _required(payload, ["employee_id", "process_id", "date", "action"])
    if payload["action"] not in {"add", "remove"}:
        raise HTTPException(status_code=422, detail="action must be add or remove")
    try:
        entry_date = date.fromisoformat(payload["date"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="date must use YYYY-MM-DD")
    if entry_date.year != year or entry_date.month != month:
        raise HTTPException(status_code=422, detail="Date is outside the selected roster month")

    domain = _ensure_roster_domain()
    employee_ids = {item["employee_id"] for item in domain["employees"]}
    process = next(
        (item for item in domain["processes"] if item["process_id"] == payload["process_id"]),
        None,
    )
    if payload["employee_id"] not in employee_ids:
        raise HTTPException(status_code=404, detail="Employee not found")
    if process is None:
        raise HTTPException(status_code=404, detail="Process not found")

    roster = get_month_roster(year, month)
    if roster is None:
        raise HTTPException(status_code=404, detail="No monthly roster has been generated")
    schedule = roster.setdefault("schedule", {})
    day_assignments = schedule.setdefault(payload["date"], {})
    assigned = set(day_assignments.setdefault(payload["process_id"], []))
    if payload["action"] == "add":
        assigned.add(payload["employee_id"])
    else:
        assigned.discard(payload["employee_id"])
    day_assignments[payload["process_id"]] = sorted(assigned)

    # Add/remove also updates the employee-level calendar used by the UI.
    employee_schedule = roster.setdefault("employee_schedule", {})
    employee_schedule.setdefault(payload["employee_id"], {})
    if payload["action"] == "add":
        employee_schedule[payload["employee_id"]][payload["date"]] = "WORK"
    else:
        employee_schedule[payload["employee_id"]][payload["date"]] = "OFF"

    validation = validate_monthly_roster(domain, year, month, schedule)
    return _invalidate_and_save(roster, validation)


@app.put("/roster/{year}/{month}/assignment")
def change_roster_assignment(year: int, month: int, payload: dict = Body(...)):
    """Change an employee/process assignment and revalidate stored roster coverage."""
    _required(payload, ["employee_id", "brand_id", "process_id", "action"])
    if payload["action"] not in {"add", "remove"}:
        raise HTTPException(status_code=422, detail="action must be add or remove")
    db = get_db()
    if not db.roster_employees.find_one({"employee_id": payload["employee_id"]}):
        raise HTTPException(status_code=404, detail="Employee not found")
    process = db.roster_processes.find_one({"process_id": payload["process_id"]}, {"_id": 0})
    if process is None:
        raise HTTPException(status_code=404, detail="Process not found")
    if process["brand_id"] != payload["brand_id"]:
        raise HTTPException(status_code=422, detail="Process does not belong to brand")

    query = {
        "employee_id": payload["employee_id"],
        "brand_id": payload["brand_id"],
        "process_id": payload["process_id"],
    }
    if payload["action"] == "add":
        if db.roster_assignments.find_one(query):
            raise HTTPException(status_code=409, detail="Assignment already exists")
        db.roster_assignments.insert_one({**query, "active": True})
    else:
        if db.roster_assignments.delete_one(query).deleted_count == 0:
            raise HTTPException(status_code=404, detail="Assignment not found")

    roster = get_month_roster(year, month)
    if roster is None:
        raise HTTPException(status_code=404, detail="No monthly roster has been generated")
    domain = _ensure_roster_domain()
    validation = validate_monthly_roster(domain, year, month, roster.get("schedule", {}))
    return _invalidate_and_save(roster, validation)


def _ensure_roster_domain():
    return _ensure_roster_data()


def _build_roster_view(roster, domain, view, filter_id):
    employees = {item["employee_id"]: item for item in domain["employees"]}
    pods = {item["pod_id"]: item for item in domain["pods"]}
    brands = {item["brand_id"]: item for item in domain["brands"]}
    processes = {item["process_id"]: item for item in domain["processes"]}
    assignments = domain["assignments"]

    if view == "company":
        return roster
    if view == "pod":
        employee_ids = {
            employee_id
            for employee_id, employee in employees.items()
            if employee["pod_id"] == filter_id
        }
        pod = pods.get(filter_id)
        if pod is None:
            raise HTTPException(status_code=404, detail="Pod not found")
    elif view == "brand":
        process_ids = {
            process["process_id"] for process in processes.values()
            if process["brand_id"] == filter_id
        }
        employee_ids = {
            item["employee_id"] for item in assignments
            if item["brand_id"] == filter_id
        }
        if filter_id not in brands:
            raise HTTPException(status_code=404, detail="Brand not found")
    elif view == "process":
        if filter_id not in processes:
            raise HTTPException(status_code=404, detail="Process not found")
        process_ids = {filter_id}
        employee_ids = {
            item["employee_id"] for item in assignments
            if item["process_id"] == filter_id
        }
    elif view == "employee":
        if filter_id not in employees:
            raise HTTPException(status_code=404, detail="Employee not found")
        employee_ids = {filter_id}
    else:
        raise HTTPException(status_code=422, detail="view must be company, pod, brand, process, or employee")

    result = dict(roster)
    if view == "pod":
        result["employee_schedule"] = {
            key: value for key, value in roster.get("employee_schedule", {}).items()
            if key in employee_ids
        }
        result["schedule"] = {
            day: {
                process_id: [employee_id for employee_id in employee_ids_for_process if employee_id in employee_ids]
                for process_id, employee_ids_for_process in day_schedule.items()
            }
            for day, day_schedule in roster.get("schedule", {}).items()
        }
        result["view_label"] = pod["name"]
    elif view in {"brand", "process"}:
        selected_process_ids = process_ids
        result["schedule"] = {
            day: {
                process_id: employee_ids_for_process
                for process_id, employee_ids_for_process in day_schedule.items()
                if process_id in selected_process_ids
            }
            for day, day_schedule in roster.get("schedule", {}).items()
        }
        result["coverage"] = {
            day: {
                process_id: coverage
                for process_id, coverage in day_coverage.items()
                if process_id in selected_process_ids
            }
            for day, day_coverage in roster.get("coverage", {}).items()
        }
        result["employee_schedule"] = {
            key: value for key, value in roster.get("employee_schedule", {}).items()
            if key in employee_ids
        }
        result["view_label"] = brands.get(filter_id, {}).get("name") if view == "brand" else processes[filter_id]["name"]
    elif view == "employee":
        result["employee_schedule"] = {
            filter_id: roster.get("employee_schedule", {}).get(filter_id, {})
        }
        result["schedule"] = {
            day: {
                process_id: [
                    employee_id for employee_id in employee_ids_for_process
                    if employee_id == filter_id
                ]
                for process_id, employee_ids_for_process in day_schedule.items()
                if filter_id in employee_ids_for_process
            }
            for day, day_schedule in roster.get("schedule", {}).items()
        }
        result["view_label"] = employees[filter_id]["name"]
    result["view"] = view
    result["filter_id"] = filter_id
    return result


@app.get("/roster/{year}/{month}/view/{view}")
def get_roster_view(year: int, month: int, view: str, filter_id: str | None = None):
    roster = get_month_roster(year, month)
    if roster is None:
        raise HTTPException(status_code=404, detail="No monthly roster has been generated")
    domain = _ensure_roster_data()
    return _build_roster_view(roster, domain, view, filter_id)
