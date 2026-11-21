"""Additive MongoDB repositories for the smart roster domain."""

from db.connection import get_db

COLLECTIONS = (
    "roster_pods",
    "roster_brands",
    "roster_processes",
    "roster_employees",
    "roster_assignments",
    "roster_holidays",
    "roster_months",
)


def replace_collection(name, documents):
    db = get_db()
    collection = db[name]
    if not isinstance(documents, list):
        raise ValueError("Replacement documents must be a list")
    if not documents:
        raise ValueError("Refusing to replace a collection with an empty document set")
    collection.delete_many({})
    if documents:
        collection.insert_many(documents)
    return len(documents)


def upsert_collection(name, documents, key):
    db = get_db()
    collection = db[name]
    for document in documents:
        collection.update_one({key: document[key]}, {"$set": document}, upsert=True)
    return len(documents)


def get_roster_domain():
    db = get_db()
    return {
        "pods": list(db.roster_pods.find({}, {"_id": 0}).sort("pod_id", 1)),
        "brands": list(db.roster_brands.find({}, {"_id": 0}).sort("brand_id", 1)),
        "processes": list(db.roster_processes.find({}, {"_id": 0}).sort("process_id", 1)),
        "employees": list(db.roster_employees.find({}, {"_id": 0}).sort("employee_id", 1)),
        "assignments": list(db.roster_assignments.find({}, {"_id": 0}).sort("employee_id", 1)),
        "holidays": list(db.roster_holidays.find({}, {"_id": 0}).sort("date", 1)),
    }


def get_month_roster(year, month):
    db = get_db()
    return db.roster_months.find_one(
        {"year": int(year), "month": int(month)}, {"_id": 0}
    )


def save_month_roster(document):
    db = get_db()
    db.roster_months.update_one(
        {"year": document["year"], "month": document["month"]},
        {"$set": document},
        upsert=True,
    )
