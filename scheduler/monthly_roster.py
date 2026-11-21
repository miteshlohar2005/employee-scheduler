"""Monthly deterministic roster scheduling engine.

Hard constraints are coverage, operating calendars, leaves, comp-offs,
availability blocks, one assignment per employee per day, and employee limits.
Weekly offs and shift preferences are soft priorities.
"""

import calendar
from itertools import combinations
from datetime import date

from ortools.sat.python import cp_model


def _date_string(day):
    return day.isoformat()


def process_operates(process, day, holiday_dates):
    day_string = _date_string(day)
    if day_string in holiday_dates:
        if process["calendar"] == "365":
            return True
        return False
    if process["calendar"] == "sunday_holiday_off":
        return day.weekday() != 6
    if process["calendar"] == "weekdays":
        return day.weekday() < 5
    return True


def _is_unavailable(employee, day):
    day_string = _date_string(day)
    if day_string in set(employee.get("availability", [])):
        return True
    if day_string in set(employee.get("leaves", [])):
        return True
    if day_string in set(employee.get("comp_offs", [])):
        return True
    return False


def _status_for_day(employee, day, holiday_dates):
    day_string = _date_string(day)
    if day_string in set(employee.get("leaves", [])):
        return "LEAVE"
    if day_string in set(employee.get("comp_offs", [])):
        return "COMP_OFF"
    if day_string in set(employee.get("availability", [])):
        return "UNAVAILABLE"
    if day_string in holiday_dates:
        return "HOLIDAY"
    if day.weekday() == employee["weekly_off"]:
        return "PREFERRED_WEEKLY_OFF"
    return "OFF"


def detect_pre_generation_conflicts(domain, year, month):
    """Explain mandatory coverage gaps before CP-SAT starts."""
    holidays = {item["date"] for item in domain["holidays"]}
    processes = [item for item in domain["processes"] if item.get("active", True)]
    employees = [item for item in domain["employees"] if item.get("active", True)]
    assignments = [item for item in domain["assignments"] if item.get("active", True)]

    assignment_by_process = {}
    for assignment in assignments:
        assignment_by_process.setdefault(assignment["process_id"], []).append(
            assignment["employee_id"]
        )

    conflicts = []
    days = calendar.monthrange(year, month)[1]
    for day_number in range(1, days + 1):
        day = date(year, month, day_number)
        for process in processes:
            if not process_operates(process, day, holidays):
                continue
            assigned_ids = set(assignment_by_process.get(process["process_id"], []))
            available_ids = {
                employee["employee_id"]
                for employee in employees
                if employee["employee_id"] in assigned_ids
                and not _is_unavailable(employee, day)
            }
            if not assigned_ids:
                conflicts.append({
                    "type": "uncovered_process",
                    "severity": "critical",
                    "date": day.isoformat(),
                    "brand_id": process["brand_id"],
                    "process_id": process["process_id"],
                    "employee_id": None,
                    "message": (
                        f"No employee is assigned to {process['name']} "
                        f"for brand {process['brand_id']}."
                    ),
                    "constraint": "mandatory",
                })
            elif len(available_ids) < process["minimum_staff"]:
                conflicts.append({
                    "type": "insufficient_staffing",
                    "severity": "critical",
                    "date": day.isoformat(),
                    "brand_id": process["brand_id"],
                    "process_id": process["process_id"],
                    "employee_id": None,
                    "message": (
                        f"{process['name']} requires {process['minimum_staff']} employee(s); "
                        f"only {len(available_ids)} available."
                    ),
                    "constraint": "mandatory",
                })
    return conflicts


def generate_monthly_roster(domain, year, month):
    """Generate a monthly draft and return explanations for any hard gap."""
    if not isinstance(year, int) or not isinstance(month, int):
        raise ValueError("Year and month must be integers")
    if month < 1 or month > 12:
        raise ValueError("Month must be between 1 and 12")

    days_in_month = calendar.monthrange(year, month)[1]
    days = [date(year, month, day_number) for day_number in range(1, days_in_month + 1)]
    holidays = {item["date"] for item in domain["holidays"]}
    processes = [item for item in domain["processes"] if item.get("active", True)]
    employees = [item for item in domain["employees"] if item.get("active", True)]
    assignments = [item for item in domain["assignments"] if item.get("active", True)]

    eligible_by_process = {}
    for process in processes:
        eligible_by_process[process["process_id"]] = []
    for assignment in assignments:
        if assignment["process_id"] in eligible_by_process:
            eligible_by_process[assignment["process_id"]].append(assignment["employee_id"])

    employee_by_id = {employee["employee_id"]: employee for employee in employees}
    for process_id in eligible_by_process:
        eligible_by_process[process_id] = list(dict.fromkeys(eligible_by_process[process_id]))

    pre_conflicts = detect_pre_generation_conflicts(domain, year, month)
    if pre_conflicts:
        # A false draft is retained only as an explicit INFEASIBLE result.
        return {
            "year": year,
            "month": month,
            "status": "INFEASIBLE",
            "can_publish": False,
            "publish_status": "draft",
            "conflicts": pre_conflicts,
            "schedule": {},
            "employee_schedule": {},
            "coverage": {},
            "message": "Roster generation stopped: mandatory coverage constraints cannot be satisfied.",
        }

    model = cp_model.CpModel()
    work = {}
    for process in processes:
        process_id = process["process_id"]
        for day in days:
            if not process_operates(process, day, holidays):
                continue
            for employee_id in eligible_by_process[process_id]:
                employee = employee_by_id[employee_id]
                if not _is_unavailable(employee, day):
                    work[(employee_id, process_id, day)] = model.NewBoolVar(
                        f"work_{employee_id}_{process_id}_{day.isoformat()}"
                    )

    # An employee can work only one brand responsibility on any date.
    process_by_id = {process["process_id"]: process for process in processes}
    for employee in employees:
        employee_id = employee["employee_id"]
        for day in days:
            employee_assignments = [
                (process_id, variable)
                for (candidate_id, process_id, candidate_day), variable in work.items()
                if candidate_id == employee_id and candidate_day == day
            ]
            for (process_a, variable_a), (process_b, variable_b) in combinations(
                employee_assignments, 2
            ):
                brand_a = process_by_id[process_a]["brand_id"]
                brand_b = process_by_id[process_b]["brand_id"]
                if brand_a != brand_b:
                    model.AddBoolOr([variable_a.Not(), variable_b.Not()])

    # Mandatory process coverage.
    for process in processes:
        process_id = process["process_id"]
        for day in days:
            if not process_operates(process, day, holidays):
                continue
            variables = [
                variable
                for (employee_id, candidate_process_id, candidate_day), variable in work.items()
                if candidate_process_id == process_id and candidate_day == day
            ]
            model.Add(sum(variables) >= process["minimum_staff"])

    objective_terms = []
    for (employee_id, _process_id, day), variable in work.items():
        employee = employee_by_id[employee_id]
        if day.weekday() == employee["weekly_off"]:
            objective_terms.append(variable * -100)
        if employee["preferences"].get("preferred_shift") == "morning":
            objective_terms.append(variable * -1)
    model.Maximize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    status = solver.Solve(model)
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return {
            "year": year,
            "month": month,
            "status": "INFEASIBLE",
            "can_publish": False,
            "publish_status": "draft",
            "conflicts": pre_conflicts or [{
                "type": "insufficient_staffing",
                "severity": "critical",
                "date": None,
                "brand_id": None,
                "process_id": None,
                "employee_id": None,
                "message": "No valid monthly roster was found with the available workforce.",
                "constraint": "mandatory",
            }],
            "schedule": {},
            "employee_schedule": {},
            "coverage": {},
            "message": "The solver could not satisfy all mandatory constraints.",
        }

    schedule = {}
    coverage = {}
    employee_schedule = {
        employee["employee_id"]: {} for employee in employees
    }
    for day in days:
        day_string = day.isoformat()
        schedule[day_string] = {}
        coverage[day_string] = {}
        for employee in employees:
            employee_schedule[employee["employee_id"]][day_string] = (
                _status_for_day(employee, day, holidays)
            )
        for process in processes:
            process_id = process["process_id"]
            if not process_operates(process, day, holidays):
                coverage[day_string][process_id] = {
                    "required": 0,
                    "actual": 0,
                    "status": "CLOSED",
                }
                continue
            assigned = [
                employee_id
                for (employee_id, candidate_process_id, candidate_day), variable in work.items()
                if candidate_process_id == process_id
                and candidate_day == day
                and solver.Value(variable) == 1
            ]
            schedule[day_string][process_id] = assigned
            coverage[day_string][process_id] = {
                "required": process["minimum_staff"],
                "actual": len(assigned),
                "status": "COVERED" if len(assigned) >= process["minimum_staff"] else "GAP",
            }
            for employee_id in assigned:
                employee_schedule[employee_id][day_string] = "WORK"

    return {
        "year": year,
        "month": month,
        "status": "FEASIBLE",
        "can_publish": True,
        "publish_status": "draft",
        "conflicts": [],
        "schedule": schedule,
        "employee_schedule": employee_schedule,
        "coverage": coverage,
        "message": "All mandatory constraints were satisfied.",
    }


def validate_monthly_roster(domain, year, month, schedule):
    """Revalidate a stored/generated schedule after leave or requirement changes."""
    holidays = {item["date"] for item in domain["holidays"]}
    employees = {item["employee_id"]: item for item in domain["employees"]}
    processes = {item["process_id"]: item for item in domain["processes"]}
    conflicts = []

    def add_resolution(conflict, resolution):
        conflict["resolution"] = resolution
        return conflict

    for day_string, process_assignments in schedule.items():
        day = date.fromisoformat(day_string)
        employee_assignments = {}
        for process_id, employee_ids in process_assignments.items():
            process = processes[process_id]
            if not process_operates(process, day, holidays):
                continue
            for employee_id in employee_ids:
                previous_process_id = employee_assignments.get(employee_id)
                if previous_process_id:
                    previous_process = processes[previous_process_id]
                    is_cross_brand_overlap = previous_process["brand_id"] != process["brand_id"]
                else:
                    is_cross_brand_overlap = False
                if is_cross_brand_overlap:
                    conflicts.append(add_resolution({
                        "type": "overlap",
                        "severity": "critical",
                        "date": day_string,
                        "brand_id": process["brand_id"],
                        "process_id": process_id,
                        "employee_id": employee_id,
                        "message": f"Employee {employee_id} is assigned to overlapping responsibilities.",
                        "constraint": "mandatory",
                    }, f"Remove {employee_id} from one of the overlapping process assignments."))
                employee_assignments[employee_id] = process_id

                employee = employees.get(employee_id)
                if employee and _is_unavailable(employee, day):
                    conflict_type = "leave_conflict"
                    if day_string in employee.get("availability", []):
                        conflict_type = "employee_unavailable"
                    conflicts.append(add_resolution({
                        "type": conflict_type,
                        "severity": "critical",
                        "date": day_string,
                        "brand_id": process["brand_id"],
                        "process_id": process_id,
                        "employee_id": employee_id,
                        "message": f"Employee {employee_id} is on leave, comp-off, or unavailable.",
                        "constraint": "mandatory",
                    }, f"Assign an eligible backup employee or update {employee_id}'s availability."))
                if employee and day.weekday() == employee.get("weekly_off"):
                    conflicts.append(add_resolution({
                        "type": "weekly_off_conflict",
                        "severity": "warning",
                        "date": day_string,
                        "brand_id": process["brand_id"],
                        "process_id": process_id,
                        "employee_id": employee_id,
                        "message": f"Employee {employee_id} is working on the preferred weekly off.",
                        "constraint": "preference",
                    }, "Move this employee to another off day or approve the exception."))
            actual = len(set(employee_ids))
            if actual < process["minimum_staff"]:
                conflicts.append(add_resolution({
                    "type": "insufficient_staffing",
                    "severity": "critical",
                    "date": day_string,
                    "brand_id": process["brand_id"],
                    "process_id": process_id,
                    "employee_id": None,
                    "message": (
                        f"{process['name']} requires {process['minimum_staff']} employee(s); "
                        f"{actual} assigned."
                    ),
                    "constraint": "mandatory",
                }, f"Add an eligible assigned employee to {process['name']} or increase available resources."))

    # Validate all required process/day combinations, including entries omitted
    # from an edited schedule.
    for day_string in schedule:
        day = date.fromisoformat(day_string)
        day_assignments = schedule[day_string]
        for process in processes.values():
            if not process_operates(process, day, holidays):
                continue
            assigned_ids = day_assignments.get(process["process_id"], [])
            actual = len(set(assigned_ids))
            if actual < process["minimum_staff"]:
                duplicate = any(
                    conflict["date"] == day_string
                    and conflict["process_id"] == process["process_id"]
                    and conflict["type"] == "insufficient_staffing"
                    for conflict in conflicts
                )
                if not duplicate:
                    conflicts.append(add_resolution({
                        "type": "insufficient_staffing",
                        "severity": "critical",
                        "date": day_string,
                        "brand_id": process["brand_id"],
                        "process_id": process["process_id"],
                        "employee_id": None,
                        "message": (
                            f"{process['name']} requires {process['minimum_staff']} employee(s); "
                            f"{actual} assigned."
                        ),
                        "constraint": "mandatory",
                    }, f"Add an eligible employee to {process['name']} for {day_string}."))

    mandatory = [conflict for conflict in conflicts if conflict["constraint"] == "mandatory"]
    return {
        "year": year,
        "month": month,
        "status": "INFEASIBLE" if mandatory else "FEASIBLE",
        "can_publish": not mandatory,
        "conflicts": conflicts,
        "message": (
            "All mandatory constraints were satisfied."
            if not mandatory
            else "Roster changes introduced mandatory constraint conflicts."
        ),
    }
