# HealthBridge build contract

Working contract for the parallel build. Governs directory ownership, ports,
env vars, DB schema, and API shapes so the Core service, AI service, and
Next.js app can be built concurrently without integration drift. Architecture
authority remains `HealthBridge-Architecture.pdf` / `CLAUDE.md` — this file
is the concrete interface layer under that spec.

## Directory ownership (do not cross these lines)

```
HealthbridgeV2/
  apps/web/              <- web-app agent ONLY
  services/core/         <- core-service agent ONLY
  services/ai/           <- ai-service agent ONLY
  rules/                 <- lead-owned, read-only for agents
  infra/                 <- lead-owned (docker-compose, wiring)
  scripts/                <- lead-owned (seed data, run scripts)
  CONTRACT.md, README.md, CLAUDE.md, .gitignore  <- lead-owned
```

Each agent creates its own `Dockerfile`, `requirements.txt`/`package.json`,
and `.env.example` inside its own directory. Do not edit files outside your
directory. Do not run `git commit`; the lead integrates and commits.

## Ports & env

| Service | Port | Env var (gateway → service) |
|---|---|---|
| apps/web (Next.js, BFF + both UIs) | 3000 | — |
| services/core (FastAPI) | 8000 | `CORE_SERVICE_URL=http://localhost:8000` |
| services/ai (FastAPI) | 8100 | `AI_SERVICE_URL=http://localhost:8100` |
| Postgres | 5432 | `DATABASE_URL=postgresql://healthbridge:healthbridge@localhost:5432/healthbridge` |
| Redis | 6379 | `REDIS_URL=redis://localhost:6379/0` |
| Ollama (host, optional) | 11434 | `OLLAMA_HOST=http://localhost:11434`, `OLLAMA_MODEL=phi4-mini` |

Auth: JWT (HS256), shared secret `JWT_SECRET` (env, demo default in
`.env.example` only, never a real secret committed). Roles: `asha`, `doctor`,
`admin`. Core service issues and verifies tokens; AI service is unauthenticated
internal-only (never exposed to clients directly, only reached via the
gateway/Core in a real deployment — for this build the gateway calls it
directly over the Docker network).

## The rule table is the single source of truth for severity

`rules/imnci-rules.v1.json` is authored once, by the lead, and must be
**read at runtime** (not hand-transcribed) by:
- `services/ai` — Python evaluator, used server-side after LLM fact extraction.
- `apps/web` — TypeScript evaluator, used on-device for the offline ASHA
  checklist fallback (per `CLAUDE.md` offline degradation rule).

Both evaluators must implement the exact grammar documented in the JSON's
`condition_grammar` key: leaf `{field, op, value}` with
`eq|neq|gt|gte|lt|lte|exists`, plus `all`/`any`/`atLeast{n, conditions}`
combinators. A field missing from the facts object is `null`; boolean leaves
against `null` are `false`; numeric comparisons against `null` are `false`.
Severity of a fact set = highest severity (`RED` > `YELLOW` > `GREEN`) among
every rule whose `when` evaluates true; if none match, use
`default_rule_id`/`default_severity` from the JSON. Never hardcode clinical
thresholds in code outside this file — if a rule needs to change, it starts
with a new `rules/imnci-rules.vN.json`, not a code edit.

**The LLM (Phi-4-mini) only ever produces a `fact_schema`-shaped JSON object.
It must never be prompted to output severity, urgency, or a color.** The rule
evaluator is the only thing allowed to decide severity.

## Data model (Postgres)

FHIR resources as JSONB (Core service owns all migrations, in
`services/core/migrations` via Alembic):

```sql
CREATE TYPE user_role AS ENUM ('asha', 'doctor', 'admin');
CREATE TYPE facility_level AS ENUM ('sub_centre', 'phc', 'district_hospital');
CREATE TYPE severity_level AS ENUM ('RED', 'YELLOW', 'GREEN');
CREATE TYPE triage_source AS ENUM ('llm', 'checklist');
CREATE TYPE token_status AS ENUM ('waiting', 'in_progress', 'done');
CREATE TYPE escalation_status AS ENUM ('open', 'acknowledged', 'resolved');
CREATE TYPE scheme_status_enum AS ENUM ('PMJAY', 'state', 'none');

CREATE TABLE facilities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  level facility_level NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role user_role NOT NULL,
  facility_id UUID REFERENCES facilities(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- FHIR Patient resource, JSONB body; abha_number is the longitudinal key
CREATE TABLE patients (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  abha_number TEXT UNIQUE NOT NULL,
  scheme_status scheme_status_enum NOT NULL DEFAULT 'none',
  fhir JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- FHIR Encounter resource per visit
CREATE TABLE encounters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id UUID NOT NULL REFERENCES patients(id),
  facility_id UUID NOT NULL REFERENCES facilities(id),
  fhir JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- FHIR Observation resource: symptoms/vitals at triage
CREATE TABLE observations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  encounter_id UUID NOT NULL REFERENCES encounters(id),
  fhir JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE queue_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  encounter_id UUID NOT NULL REFERENCES encounters(id),
  facility_id UUID NOT NULL REFERENCES facilities(id),
  token_number INTEGER NOT NULL,
  severity severity_level NOT NULL,
  status token_status NOT NULL DEFAULT 'waiting',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE triage_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  encounter_id UUID NOT NULL REFERENCES encounters(id),
  complaint_text TEXT,
  extracted_facts JSONB NOT NULL,
  rule_id TEXT NOT NULL,
  rule_version TEXT NOT NULL,
  severity severity_level NOT NULL,
  source triage_source NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE escalation_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  triage_record_id UUID NOT NULL REFERENCES triage_records(id),
  patient_id UUID NOT NULL REFERENCES patients(id),
  facility_id UUID NOT NULL REFERENCES facilities(id),
  status escalation_status NOT NULL DEFAULT 'open',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_user_id UUID REFERENCES users(id),
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id UUID,
  details JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Every triage decision (any severity) writes one `audit_log` row naming
`rule_id`, `rule_version`, the input, and the extracted facts — no exceptions.

## Core service API (`services/core`, FastAPI, port 8000)

Core is the only thing that writes to Postgres. It never calls the AI
service and never blocks on it.

- `POST /auth/login` `{username, password}` → `{token, role, facility_id}`
- `POST /patients` `{abha_number, name, dob, gender, scheme_status}` → FHIR Patient
- `GET /patients/{abha_number}` → FHIR Patient + list of Encounters
- `POST /encounters` `{abha_number, facility_id, chief_complaint}` → FHIR Encounter (also creates a `waiting` queue_token)
- `POST /triage` `{encounter_id, complaint_text, source: "llm"|"checklist", extracted_facts, severity, rule_id, rule_version, actor_user_id}` → writes `triage_records` + `observations`, reorders `queue_tokens` for the facility, and if `severity == "RED"` creates an `escalation_events` row; always writes `audit_log`. Returns `{triage_record, queue_position, escalation_created}`.
- `GET /queue/{facility_id}` → tokens ordered `RED` → `YELLOW` → `GREEN`, then FIFO within severity
- `GET /escalations/{facility_id}` → open escalations
- `POST /escalations/{id}/acknowledge` → sets `acknowledged`
- `GET /dashboard/{facility_id}` → `{triaged_by_severity: {RED, YELLOW, GREEN}, queue_length, teleconsults_done, red_cases_escalated}`
- `GET /abdm/patient/{abha_number}` → delegates to `MockAbdmClient` (in `services/core/adapters/`), returns a sandbox-shaped FHIR bundle. This adapter is the seam a real ABDM gateway client swaps into later — do not inline mock logic elsewhere.

## AI service API (`services/ai`, FastAPI, port 8100)

Stateless. Never touches Postgres. Returns severity + facts only; Core
persists everything.

- `POST /triage/extract` `{complaint_text?: string, audio_base64?: string, age_months?: number}` →
  1. If `audio_base64` present: transcribe locally (Whisper wrapper; lazy-loaded, optional dependency — if the model isn't available, return `503` so the caller falls back to the checklist path, never a stack trace).
  2. Run the complaint text through Phi-4-mini via Ollama (LangGraph graph), prompted to emit **only** a JSON object matching `rules/imnci-rules.v1.json`'s `fact_schema` — facts, never severity.
  3. Run the shared rule evaluator against those facts.
  4. Return `{transcript?, extracted_facts, severity, rule_id, rule_version}`.
  - If Ollama is unreachable, return `503 {"detail": "ai_unavailable"}` — the gateway/app must treat this as "skip LLM, use checklist," per `CLAUDE.md` offline degradation.
- `GET /health` → `{ollama_reachable: bool, whisper_available: bool}`

## Gateway / BFF (`apps/web/app/api/**`, Next.js route handlers)

Both client surfaces (ASHA PWA, Facility web) call only these routes; they
never call Core or AI directly (matches the architecture diagram).

- `POST /api/auth/login` → proxies Core
- `POST /api/patients`, `GET /api/patients/[abha]` → proxies Core
- `POST /api/encounters` → proxies Core
- `POST /api/triage/extract` → proxies AI service; on `503`/network error, returns `{ai_unavailable: true}` so the client falls back to the on-device checklist evaluator
- `POST /api/triage` → proxies Core `/triage` (used for both the LLM path, after `/api/triage/extract`, and the offline checklist path where the client already computed severity on-device)
- `GET /api/queue/[facilityId]`, `GET /api/escalations/[facilityId]`, `POST /api/escalations/[id]/acknowledge`, `GET /api/dashboard/[facilityId]` → proxy Core

## Non-negotiables carried over from CLAUDE.md

- AI service never writes Postgres directly.
- Every triage decision, every severity, gets an `audit_log` row.
- Offline: the ASHA app's on-device TS rule evaluator over
  `rules/imnci-rules.v1.json` is the fallback — not a second, different rule
  set.
- No cloud LLM, no hosted vector DB, nothing in the offline critical path
  that requires connectivity.
- `MockAbdmClient` is the only ABDM integration point; it sits behind an
  adapter interface in `services/core/adapters/`.
