# Technical approach note

The solution preserves the existing weekly store scheduling engine and builds a separate monthly roster domain around MongoDB and OR-Tools. The monthly engine models process coverage, calendars, holidays, employee availability, leave, comp-offs, assignments, and overlap constraints as boolean variables.

Mandatory requirements are separated from preferences. Weekly offs and preferred shifts can be optimized rather than overriding minimum coverage. Every generated or edited roster is revalidated before publication. This prevents the interface from presenting an infeasible roster as publishable.

FastAPI exposes the domain and roster workflows. React presents overview, management, conflict, and calendar views over the same backend data. MongoDB remains an appendable working store, so existing `/stores` and `/schedule/{store_id}` functionality is not replaced.
