# Datastraw Smart Roster Management System

A browser-based workforce planning application built for the Datastraw AI + Tech Internship Assessment. It combines a preserved OR-Tools weekly store scheduler with a monthly multi-brand operations roster, configurable staffing rules, conflict explanations, CRUD management, and an enterprise SaaS interface.

## Run locally

Requirements: Python 3.11+, Node.js 20+, and MongoDB.

```powershell
python -m venv venv
.\\venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `MONGO_URI`, `MONGO_DB_NAME`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and `CORS_ORIGINS` in `.env`.

```powershell
python -m db.seed_data
python -m db.roster_seed
python -m uvicorn api.main:app --reload --port 8000
```

Start the frontend in a second terminal:

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Use **Admin sign in** for roster publication and management mutations.

## Docker

Set `ADMIN_PASSWORD` and optional frontend/API values, then run:

```powershell
docker compose up --build
```

Frontend: `http://localhost:8080`; API: `http://localhost:8000`.

## Architecture

```text
React/Vite UI
     |
     v
FastAPI + bearer-token admin authentication
     |
     +--> MongoDB domain collections
     +--> Monthly OR-Tools CP-SAT roster engine
     +--> Existing weekly store CP-SAT engine
     +--> Excel import and preset data
```

MongoDB collections: `stores`, `employees`, `roster_pods`, `roster_brands`, `roster_processes`, `roster_employees`, `roster_assignments`, `roster_holidays`, and `roster_months`.

## Scheduling algorithm

The monthly solver models one date/process assignment as a boolean variable. Mandatory constraints enforce:

- Process operating calendar
- Public-holiday exceptions
- Minimum process staffing
- Leave, comp-off, and unavailable blocking
- One cross-brand responsibility per employee per date
- 365-day, weekday, and Sunday/holiday-off calendars

Preferred weekly-offs and morning preferences are optimized softly. A generated draft is infeasible when mandatory constraints cannot be satisfied. Validation is repeated after edits and before publishing.

The existing weekly scheduler remains independent. It continues to use CP-SAT for store hourly coverage, peak staffing, shift continuity, shift lengths, and weekly store budgets.

## Assumptions

- Calendar values are `365`, `weekdays`, or `sunday_holiday_off`.
- `weekly_off` is a Monday-indexed weekday where 0 is Monday and 6 is Sunday.
- Employee and process sample data is fictional/demo data.
- Cross-brand employee overlap is prohibited on the same date.
- Multiple processes for the same brand may be combined for one employee.
- A published roster is blocked until revalidation succeeds.
- Weekly offs are preferences; mandatory coverage takes priority.
- Bearer tokens are demo/in-memory sessions and must be replaced by an identity provider for enterprise production.

## Datastraw: How We Think

1. **How did you model employees, brands, processes, pods, and relationships?**
   Pods own employees through `pod_id`; brands own processes; employee/process links are represented by assignment documents containing employee, brand, and process IDs. Leaves and availability belong to employee documents, while operational calendars belong to processes.

2. **How does the system generate and validate a roster?**
   It validates the month and operating data, computes each process's required days, blocks unavailable employees, solves daily/process coverage with OR-Tools CP-SAT, and returns structured coverage/conflict results. Revalidation rechecks every stored assignment, leave, overlap, and process staffing requirement before publish.

3. **How are single-resource and multi-resource brands handled?**
   Both use the same assignment model. A single-resource brand assigns one employee to every process. Multi-resource brands assign two or three employees to separate or overlapping processes. Staffing is evaluated per process, not merely per brand.

4. **What happens when a sole employee is unavailable?**
   Generation detects an available-employee deficit or revalidation detects the changed assignment as a leave/unavailability conflict. The response lists affected processes and dates and suggests assigning an eligible backup or updating availability.

5. **How are conflicting requirements and insufficient staffing handled?**
   Mandatory conflicts are returned with severity, date, brand, process, employee, explanation, and resolution. Publishing is blocked while any mandatory conflict remains. Weekly-off and shift preference conflicts remain warnings.

6. **What is automated versus human-controlled?**
   Generation, coverage checking, leave validation, overlap detection, and publish blocking are automated. Managers approve leave, change assignments and calendars, resolve real-world exceptions, and publish validated rosters.

7. **What would change if the company doubled in scale?**
   I would add MongoDB indexes, pagination, background job scheduling, a persistent authenticated user service, audit/version tables, multi-tenant organization boundaries, and distributed solver workers. The roster UI would virtualize large calendars.

8. **What would be improved with another week?**
   I would add backup-resource ranking, roster approval workflows, notifications, Excel/CSV export, change-history/audit, alternative-plan comparison, email delivery, and automated end-to-end browser regression coverage.

## Security

- Read APIs remain public for demo access.
- Mutation, publish, delete, upload, and management APIs require an authenticated admin bearer session.
- CORS is restricted by `CORS_ORIGINS`.
- Set a strong `ADMIN_PASSWORD`; never commit `.env`.
- The demo bearer implementation uses in-memory tokens. Replace it with OAuth/OIDC or an enterprise identity provider before high-trust production use.

## Testing

```powershell
venv\Scripts\python.exe -m pytest tests/test_monthly_roster.py tests/test_phase3_api.py tests/test_scheduler.py -q
cd frontend
npm run lint
npm run build
```

## License

See [LICENSE](./LICENSE). Third-party attribution is listed in [NOTICE](./NOTICE).
