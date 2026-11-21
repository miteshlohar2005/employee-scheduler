"""Configurable domain models for monthly roster management.

These documents are additive to the existing store/employee data model.
"""

CALENDARS = {"365", "weekdays", "sunday_holiday_off"}
CONFLICT_TYPES = {
    "uncovered_process",
    "insufficient_staffing",
    "leave_conflict",
    "weekly_off_conflict",
    "overlap",
    "incompatible_shift",
}


def validate_calendar(calendar):
    if calendar not in CALENDARS:
        raise ValueError(f"Unknown operating calendar: {calendar!r}")


def build_pod(pod_id, name, lead_employee_id):
    if not all([pod_id, name, lead_employee_id]):
        raise ValueError("Pod fields must not be empty")
    return {"pod_id": pod_id, "name": name, "lead_employee_id": lead_employee_id}


def build_brand(brand_id, name):
    if not all([brand_id, name]):
        raise ValueError("Brand fields must not be empty")
    return {"brand_id": brand_id, "name": name, "active": True}


def build_process(process_id, brand_id, name, calendar, minimum_staff=1):
    validate_calendar(calendar)
    if not isinstance(minimum_staff, int) or minimum_staff < 1:
        raise ValueError("minimum_staff must be a positive integer")
    if not all([process_id, brand_id, name]):
        raise ValueError("Process fields must not be empty")
    return {
        "process_id": process_id,
        "brand_id": brand_id,
        "name": name,
        "calendar": calendar,
        "minimum_staff": minimum_staff,
    }


def build_roster_employee(
    employee_id,
    name,
    pod_id,
    weekly_off=6,
    employment_type="full_time",
    availability=None,
    leaves=None,
    comp_offs=None,
    preferences=None,
):
    if employment_type not in {"full_time", "part_time"}:
        raise ValueError("employment_type must be full_time or part_time")
    if not 0 <= weekly_off <= 6:
        raise ValueError("weekly_off must be a weekday index from 0 (Monday)")
    return {
        "employee_id": employee_id,
        "name": name,
        "pod_id": pod_id,
        "employment_type": employment_type,
        "weekly_off": weekly_off,
        "availability": availability or [],
        "leaves": leaves or [],
        "comp_offs": comp_offs or [],
        "preferences": preferences or {},
        "active": True,
    }


def build_assignment(employee_id, brand_id, process_id):
    if not all([employee_id, brand_id, process_id]):
        raise ValueError("Assignment fields must not be empty")
    return {
        "employee_id": employee_id,
        "brand_id": brand_id,
        "process_id": process_id,
        "active": True,
    }
