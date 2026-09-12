# HealthBridge Core service

FastAPI, port 8000. The only component that writes to Postgres. Never calls
the AI service. See `../../CONTRACT.md` for the full API/DB contract this
implements.

## Local run (without Docker)

```bash
cd services/core
python -m venv .venv
. .venv/Scripts/activate   # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env       # edit DATABASE_URL/REDIS_URL/JWT_SECRET if needed
alembic upgrade head       # requires a reachable Postgres
uvicorn app.main:app --reload --port 8000
```

`GET /health` reports `db_reachable`/`redis_reachable` independently, and the
app boots even if both are down (see `app/db.py`, `app/redis_client.py`) --
Postgres/Redis are required for real requests, not for the process to start.

## Tests

```bash
pytest
```

Covers logic that doesn't require a live database: FHIR resource builders,
JWT encode/decode round-trip, password hashing, and `MockAbdmClient`
determinism. Endpoint/DB-integration behavior (queue reordering, audit log
writes, escalation creation) is implemented in `app/routers/triage.py` and
`app/routers/queue.py` but requires a live Postgres to exercise end-to-end --
not available in the build sandbox this was written in.

## Docker

```bash
docker build -t healthbridge-core .
docker run -p 8000:8000 --env-file .env healthbridge-core
```
