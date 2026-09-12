# HealthBridge

An offline-capable, ASHA-operated, ABDM/FHIR-linked record that follows a rural
patient across every level of the public health system — sub-centre, PHC,
district hospital — with explainable danger-sign triage that reorders the
queue and escalates emergencies.

Built for the SIH problem statement on rural & underserved healthcare access.
Strengthens the public system; does not replace it.

**Status:** thin vertical spine built end-to-end — Core service, AI service,
and the Next.js app (ASHA PWA + facility web + BFF) all exist and pass their
own test suites. Not yet run as a live integrated stack (no Docker/Postgres/
Ollama in the build environment — see "Manual setup required" below). See
[`CLAUDE.md`](./CLAUDE.md) for the architecture and rules that govern this
repo, and [`CONTRACT.md`](./CONTRACT.md) for the concrete API/DB/rule-engine
interface the three components are built against.

## Source of truth

`HealthBridge-Architecture.pdf` in this directory is the governing spec.
`CLAUDE.md` is a working transcription of it for agent/dev use — if the two
ever disagree, the PDF wins and `CLAUDE.md` should be corrected.

## What's real vs. mocked

One real vertical spine, demoed end to end, beats eight shallow modules.

**Built real:** patient record (FHIR-shaped, keyed by ABHA number), digital
triage engine (LLM extraction + IMNCI rule table), severity-based queue with
red-case auto-escalation, facility dashboard (4 tiles, real data), offline-first
ASHA app (PWA with local sync).

**Convincing mock, behind an adapter:** ABDM gateway (`MockAbdmClient`),
teleconsult (store-and-forward only), scheme verification (a status badge),
referral/diagnostics/medicine-stock/follow-up (data screens only).

## Stack

- **Frontend:** Next.js (App Router), TypeScript, Tailwind CSS — one framework
  for both client surfaces and the API gateway (BFF).
- **Backend:** FastAPI (Python), REST — split into a deterministic **Core**
  service and a separate **AI** service so a slow/offline model never blocks
  a patient record from saving.
- **AI:** Phi-4-mini via Ollama, LangGraph, Whisper — all local, zero
  connectivity required.
- **Data:** PostgreSQL (FHIR resources as JSONB), Redis (priority queue +
  escalation pub/sub).

## Build order

1. **Spine:** auth + roles, FHIR-shaped Patient record, create-patient flow.
2. **Triage:** LLM extract → rule engine → severity, matched rule shown in UI.
3. **Queue & escalation:** severity-based reorder, RED auto-escalation.
4. **Dashboard:** four real-data tiles.
5. **Offline:** full ASHA flow offline, sync on reconnect.
6. **Mocks & polish:** teleconsult, scheme badge, seeded demo data.

If behind schedule, cut in reverse order — mocks first, offline second, the
triage spine never.

## Project structure

```
apps/web/           Next.js (App Router, TS, Tailwind) — ASHA PWA + facility
                     web + the BFF/gateway (app/api/**), all in one app.
services/core/       FastAPI. Owns Postgres. Patients, encounters, triage,
                     queue, escalations, dashboard, audit log, MockAbdmClient.
services/ai/         FastAPI. Stateless. Whisper -> Phi-4-mini (Ollama, via
                     LangGraph) -> rule engine. Never touches Postgres.
rules/               rules/imnci-rules.v1.json — the versioned IMNCI danger-
                     sign rule table. Single source of truth for severity,
                     read at runtime by both services/ai (Python) and
                     apps/web (TypeScript, for the offline on-device path).
infra/               docker-compose.yml wiring Postgres, Redis, both
                     services, and the web app together.
scripts/             Demo seed data (facilities/users SQL, and a Python
                     script that seeds patients through the real Core API).
CONTRACT.md          Ports, env vars, DB schema, and API shapes the three
                     components above were built against.
```

## Getting started

### Option A — Docker Compose (once Docker is installed)

```bash
cp .env.example .env   # edit JWT_SECRET if you want; defaults work for a demo
cd infra && docker compose up --build
# then, once containers are healthy, from the repo root:
psql "$DATABASE_URL" -f scripts/seed_facilities_and_users.sql   # or run inside the postgres container
python scripts/seed_demo_patients.py
```

Ollama (for real LLM extraction) runs on the host, not in Compose — install
it separately and `ollama pull phi4-mini`. Without it, the AI service
degrades cleanly to `503 ai_unavailable` and the ASHA app falls back to the
on-device structured checklist, per `CLAUDE.md`.

### Option B — run each piece manually (no Docker)

Each of `services/core/`, `services/ai/`, and `apps/web/` has its own
`README.md` with exact commands. In short: a Postgres + Redis instance
reachable at the URLs in `.env.example`, then per service:

```bash
# services/core and services/ai
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000   # or 8100 for services/ai

# apps/web
npm install
cp .env.example .env.local
npm run dev   # http://localhost:3000
```

Demo logins (after running `scripts/seed_facilities_and_users.sql`):
`asha1` / `asha-demo-pass`, `doctor1` / `doctor-demo-pass`, `admin1` /
`admin-demo-pass`.

## Owner

Shaurya Batish
