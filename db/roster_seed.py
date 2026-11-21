"""Seed realistic additive roster-management sample data.

This module never deletes or overwrites the existing stores/employees collections.
"""

from db.roster_repositories import replace_collection, upsert_collection
from models.roster_domain import (
    build_assignment,
    build_brand,
    build_pod,
    build_process,
    build_roster_employee,
)

BRAND_NAMES = [
    (f"B{index}", name)
    for index, name in enumerate([
        "Northstar Retail", "UrbanCart", "FreshNest", "Velora Fashion",
        "GreenGrocer", "PetPulse", "HomeAura", "SwiftMart",
        "Medora Health", "TechTrek", "CloudNine Books", "Luma Beauty",
        "Atlas Sports", "Oak & Linen", "Nova Gadgets", "PurePantry",
        "DailyDose", "MintWorks", "BrightKids", "Cedar Outdoors",
        "Silverline", "AutoBloom", "PixelMart", "Kindred Home",
        "FitFoundry", "Wanderly", "EcoEssentials", "PeakValue",
        "JoyBox", "MetroSupply",
    ], start=1)
]

PROCESS_NAMES = (
    ("CS", "Customer Support"),
    ("ACC", "Abandoned Cart"),
    ("RET", "Retention"),
    ("NDR", "Non-Delivery Reports"),
    ("QA", "Quality Operations"),
)


def build_seed_data():
    pods = [
        build_pod("P1", "Pod Alpha", "EMP001"),
        build_pod("P2", "Pod Beta", "EMP009"),
        build_pod("P3", "Pod Gamma", "EMP018"),
        build_pod("P4", "Pod Delta", "EMP027"),
    ]
    brands = [build_brand(*brand) for brand in BRAND_NAMES]

    processes = []
    for index, (brand_id, _name) in enumerate(BRAND_NAMES, start=1):
        processes.append(build_process(f"{brand_id}-CS", brand_id, "Customer Support", "365", 1))
        if index in {2, 5, 7, 9, 10}:
            processes.append(build_process(f"{brand_id}-ACC", brand_id, "Abandoned Cart", "weekdays", 1))
        if index in {3, 6, 9, 10}:
            processes.append(build_process(f"{brand_id}-NDR", brand_id, "Non-Delivery Reports", "sunday_holiday_off", 1))
        if index in {9, 10}:
            processes.append(build_process(f"{brand_id}-RET", brand_id, "Retention", "sunday_holiday_off", 1))

    employees = []
    employee_count = 36
    first_names = [
        "Aarav", "Vivaan", "Ishita", "Diya", "Kabir", "Meera", "Arjun", "Ananya",
        "Reyansh", "Saanvi", "Aditya", "Kiara", "Rohan", "Aisha", "Yash", "Nisha",
        "Vihaan", "Tara", "Dhruv", "Priya", "Kunal", "Maya", "Rahul", "Sara",
        "Manav", "Riya", "Nikhil", "Pooja", "Jay", "Sneha", "Harsh", "Ira",
        "Siddharth", "Neha", "Dev", "Kavya",
    ]
    last_names = [
        "Sharma", "Patel", "Singh", "Iyer", "Khan", "Mehta", "Das", "Joshi",
    ]
    brand_employee_counts = [1] * 24 + [2] * 6

    employee_index = 0
    assignments = []
    brand_assignment_map = {}
    for brand_index, ((brand_id, _brand_name), count) in enumerate(
        zip(BRAND_NAMES, brand_employee_counts), start=1
    ):
        brand_processes = [process for process in processes if process["brand_id"] == brand_id]
        assigned_employees = []
        for _ in range(count):
            employee_id = f"EMP{employee_index + 1:03d}"
            pod_id = f"P{(employee_index % 4) + 1}"
            weekly_off = (employee_index * 2 + brand_index) % 7
            employment_type = "part_time" if employee_index % 7 == 0 else "full_time"
            employee = build_roster_employee(
                employee_id,
                f"{first_names[employee_index]} {last_names[employee_index % len(last_names)]}",
                pod_id,
                weekly_off=weekly_off,
                employment_type=employment_type,
                preferences={"preferred_shift": "morning" if employee_index % 3 else "flexible"},
            )
            employees.append(employee)
            assigned_employees.append(employee_id)

            if count == 1:
                for process in brand_processes:
                    assignments.append(build_assignment(
                        employee_id, brand_id, process["process_id"]
                    ))
            else:
                process_for_employee = brand_processes[
                    employee_index % len(brand_processes)
                ]
                assignments.append(build_assignment(
                    employee_id, brand_id, process_for_employee["process_id"]
                ))

            # Multi-resource brands use overlapping assignments and explicit secondary process work.
            if count > 1 and len(brand_processes) > 1:
                secondary = brand_processes[(employee_index + 1) % len(brand_processes)]
                if secondary["process_id"] != process_for_employee["process_id"]:
                    assignments.append(build_assignment(
                        employee_id, brand_id, secondary["process_id"]
                    ))

            employee_index += 1
        brand_assignment_map[brand_id] = assigned_employees

    holidays = [
        {"date": "2026-01-26", "name": "Republic Day", "scope": "India"},
        {"date": "2026-03-14", "name": "Holi", "scope": "India"},
        {"date": "2026-04-03", "name": "Good Friday", "scope": "India"},
        {"date": "2026-05-01", "name": "Labour Day", "scope": "India"},
        {"date": "2026-08-15", "name": "Independence Day", "scope": "India"},
        {"date": "2026-10-02", "name": "Gandhi Jayanti", "scope": "India"},
        {"date": "2026-10-20", "name": "Diwali", "scope": "India"},
        {"date": "2026-12-25", "name": "Christmas", "scope": "India"},
    ]

    # Add realistic one-time leave examples used in change scenarios.
    for employee in employees:
        index = int(employee["employee_id"][3:])
        if index % 11 == 0:
            employee["leaves"] = ["2026-12-10"]
        if index % 13 == 0:
            employee["comp_offs"] = ["2026-12-18"]
        if index % 8 == 0:
            employee["availability"] = ["2026-12-04"]

    return {
        "pods": pods,
        "brands": brands,
        "processes": processes,
        "employees": employees,
        "assignments": assignments,
        "holidays": holidays,
    }


def seed_roster_data():
    data = build_seed_data()
    counts = {
        "pods": upsert_collection("roster_pods", data["pods"], "pod_id"),
        "brands": upsert_collection("roster_brands", data["brands"], "brand_id"),
        "processes": upsert_collection("roster_processes", data["processes"], "process_id"),
        "employees": upsert_collection("roster_employees", data["employees"], "employee_id"),
        "assignments": replace_collection("roster_assignments", data["assignments"]),
        "holidays": upsert_collection("roster_holidays", data["holidays"], "date"),
    }
    return counts


if __name__ == "__main__":
    print(seed_roster_data())
