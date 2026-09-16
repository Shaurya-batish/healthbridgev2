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
-- Real verification state, distinct from the ASHA's self-reported claim
-- above -- see docs/REAL-INTEGRATION-AUDIT.md. Only moved off 'unverified'
-- by a real NHA BIS call; never fabricated.
CREATE TYPE scheme_verification_status AS ENUM ('unverified', 'pending', 'verified', 'failed');
CREATE TYPE referral_status AS ENUM ('pending', 'accepted', 'completed', 'cancelled');
CREATE TYPE diagnostic_status AS ENUM ('ordered', 'in_progress', 'completed', 'cancelled');
CREATE TYPE stock_movement_reason AS ENUM ('restock', 'dispensed', 'adjustment');
CREATE TYPE follow_up_status AS ENUM ('scheduled', 'completed', 'missed', 'cancelled');
CREATE TYPE teleconsult_status AS ENUM ('pending', 'recorded', 'reviewed');

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
  scheme_verification_status scheme_verification_status NOT NULL DEFAULT 'unverified',
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

-- Real internal workflows (2026-09-13 no-mock policy). None of these need
-- an external credential -- same-system operational data, same category
-- as queue_tokens/escalation_events above.

CREATE TABLE referrals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id UUID NOT NULL REFERENCES patients(id),
  encounter_id UUID NOT NULL REFERENCES encounters(id),
  from_facility_id UUID NOT NULL REFERENCES facilities(id),
  to_facility_id UUID NOT NULL REFERENCES facilities(id),
  reason TEXT NOT NULL,
  status referral_status NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE diagnostic_orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  encounter_id UUID NOT NULL REFERENCES encounters(id),
  facility_id UUID NOT NULL REFERENCES facilities(id),
  test_name TEXT NOT NULL,
  status diagnostic_status NOT NULL DEFAULT 'ordered',
  result_text TEXT,
  result_recorded_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE medicine_stock (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  facility_id UUID NOT NULL REFERENCES facilities(id),
  medicine_name TEXT NOT NULL,
  unit TEXT NOT NULL DEFAULT 'units',
  quantity_on_hand INTEGER NOT NULL DEFAULT 0,
  reorder_threshold INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (facility_id, medicine_name)
);

-- Append-only ledger. quantity_on_hand above is always reconstructable as
-- the sum of these -- a real audit trail, never a bare mutable counter.
CREATE TABLE medicine_stock_movements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stock_id UUID NOT NULL REFERENCES medicine_stock(id),
  change_qty INTEGER NOT NULL,
  reason stock_movement_reason NOT NULL,
  actor_user_id UUID REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE follow_ups (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id UUID NOT NULL REFERENCES patients(id),
  encounter_id UUID NOT NULL REFERENCES encounters(id),
  facility_id UUID NOT NULL REFERENCES facilities(id),
  scheduled_date DATE NOT NULL,
  reason TEXT NOT NULL,
  status follow_up_status NOT NULL DEFAULT 'scheduled',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Migrations 0005/0006 (2026-09-15) add, in summary:
--   complaint_captures      provenance of every confirmed typed/voice complaint
--                           (input source, selected language, first captured
--                           text, machine translation + engine, ASHA-confirmed
--                           original and English, capture/confirm/consent
--                           timestamps, audio sha256/duration/mime -- never the
--                           audio). client_capture_id UNIQUE.
--   medicine_sources        dataset provenance (url, licence, sha256, version,
--                           price basis, counts). One row per dataset name.
--   medicines               imported identity: brand, derived generic, form,
--                           route, release type, pack qty/unit, price, unit
--                           price, discontinued, match_status, match_key.
--   medicine_ingredients    ingredient name + normalised strength per medicine.
--   medicine_stock.medicine_id  FK linking existing inventory to an identity.
--   medication_orders       doctor-authored, versioned prescription lines.
--   substitution_requests   pending -> approved | rejected | invalidated;
--                           partial UNIQUE (order_id, proposed_medicine_id)
--                           WHERE status = 'pending'.
-- See services/core/migrations/versions/0005_*.py and 0006_*.py for columns.

-- Real self-hosted store-and-forward teleconsult. media_path points at a
-- real file on disk under TELECONSULT_MEDIA_DIR; media_checksum_sha256 is
-- computed from the real uploaded bytes.
CREATE TABLE teleconsults (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  encounter_id UUID NOT NULL REFERENCES encounters(id),
  patient_id UUID NOT NULL REFERENCES patients(id),
  facility_id UUID NOT NULL REFERENCES facilities(id),
  requested_by_user_id UUID REFERENCES users(id),
  status teleconsult_status NOT NULL DEFAULT 'pending',
  media_path TEXT,
  media_content_type TEXT,
  media_size_bytes INTEGER,
  media_checksum_sha256 TEXT,
  doctor_response_text TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
- `GET /dashboard/{facility_id}` → `{triaged_by_severity: {RED, YELLOW, GREEN}, queue_length, teleconsults_done, red_cases_escalated}` — `teleconsults_done` counts real `teleconsults` rows with `status = 'reviewed'`.
- `GET /abdm/patient/{abha_number}` → delegates to `AbdmGatewayClient` (in `services/core/app/adapters/abdm_client.py`), a real client built against the ABDM Gateway's session-token + care-context-discovery API shape. Returns `501 {"detail": "abdm_not_configured"}` when NHA credentials aren't set (never a fabricated bundle) or `502 {"detail": "abdm_unavailable"}` on a real call failure. See `docs/REAL-INTEGRATION-AUDIT.md`.
- `POST /patients/{abha_number}/verify-scheme` → delegates to `NhaBeneficiaryClient` (real PM-JAY BIS client shape). Returns `501 {"detail": "scheme_verification_not_configured"}` when NHA operator credentials aren't set; only ever sets `scheme_verification_status` to `verified`/`failed` on a real call succeeding.
- `POST /referrals`, `GET /referrals/facility/{facility_id}`, `GET /referrals/patient/{patient_id}`, `POST /referrals/{id}/status` → real cross-facility referral tracking.
- `POST /diagnostics`, `GET /diagnostics/facility/{facility_id}`, `POST /diagnostics/{id}/status`, `POST /diagnostics/{id}/result` → real diagnostic order/result workflow.
- `POST /medicine-stock`, `GET /medicine-stock/facility/{facility_id}`, `POST /medicine-stock/{id}/adjust`, `GET /medicine-stock/{id}/movements` → real inventory; every quantity change writes an append-only `medicine_stock_movements` row.
- `POST /follow-ups`, `GET /follow-ups/facility/{facility_id}?due_by=`, `GET /follow-ups/patient/{patient_id}`, `POST /follow-ups/{id}/status` → real follow-up scheduling.
- `POST /teleconsults`, `GET /teleconsults/facility/{facility_id}`, `POST /teleconsults/{id}/media` (real multipart file upload), `GET /teleconsults/{id}/media` (real file download/playback), `POST /teleconsults/{id}/response` → real self-hosted store-and-forward teleconsult.
- `POST /triage` additionally accepts optional `complaint_capture` (typed/voice provenance, see `ComplaintCaptureIn`). When present, `complaint_text` must equal `complaint_capture.confirmed_text_en`; stale or inconsistent captures are refused with 422 and nothing is written; a replayed `client_capture_id` is 409 `complaint_capture_already_recorded`. The capture is written in the same transaction as the triage record and copied into the `triage_decision` audit row.
- `GET /medicines?q=&limit=&offset=` → search imported reference medicines (brand or ingredient; `q` 2–100 chars, `limit` ≤ 50, `offset` ≤ 10000).
- `GET /medicines/{id}` → one medicine with structured ingredients and source provenance.
- `GET /medicines/{id}/substitutes?facility_id=` → facility-scoped, informational same-composition comparison: exact ingredient set + normalised strengths + form + route + release type (fails closed), real stock status per candidate (`available`/`unavailable`/`stale`/`unknown`), comparable unit price and saving (strictly cheaper only), ranked over the whole match group, top 100 returned with `total_candidates`.
- `POST /medicine-stock/{id}/link` `{medicine_id | null}` → link existing inventory to an identity (audited, never changes quantity).
- `POST /medication-orders` (doctor only) `{encounter_id, medicine_id, instructions}`; `GET /medication-orders/{id}`; `GET /medication-orders/patient/{patient_id}?facility_id=`.
- `POST /substitution-requests` `{order_id, proposed_medicine_id, note?}` (any role with facility access; creates a pending request, changes nothing); `GET /substitution-requests/facility/{facility_id}?status=`; `POST /substitution-requests/{id}/approve` and `/reject` (doctor at that facility only). Approval re-validates under row locks and supersedes the order through the prescribing path; a changed prescription or broken match marks the request `invalidated` (409).

## AI service API (`services/ai`, FastAPI, port 8100)

Stateless. Never touches Postgres. Returns severity + facts only; Core
persists everything.

- `POST /triage/extract` `{complaint_text?: string, audio_base64?: string, age_months?: number}` →
  1. If `audio_base64` present: transcribe locally (Whisper wrapper; lazy-loaded, optional dependency — if the model isn't available, return `503` so the caller falls back to the checklist path, never a stack trace).
  2. Run the complaint text through Phi-4-mini via Ollama (LangGraph graph), prompted to emit **only** a JSON object matching `rules/imnci-rules.v1.json`'s `fact_schema` — facts, never severity.
  3. Run the shared rule evaluator against those facts.
  4. Return `{transcript?, extracted_facts, severity, rule_id, rule_version}`.
  - If Ollama is unreachable, return `503 {"detail": "ai_unavailable"}` — the gateway/app must treat this as "skip LLM, use checklist," per `CLAUDE.md` offline degradation.
- `POST /transcribe` `{audio_base64, language, mime_type?}` → `{transcript, translation_en, language, engine, model, duration_seconds}`. Text only, never a severity. 422 `invalid_audio` / `audio_too_short` / `audio_too_long` / `unsupported_audio_format` / `empty_transcript`; 503 `transcription_unavailable`.
- `POST /translate` `{text, source_language}` → `{translation_en, source_language, engine, engine_version}` via local Argos Translate for TYPED complaints. 503 `{code: translation_unavailable, reason: language_not_installed | engine_not_installed | degraded_mode | translation_failed}`.
- `GET /health` → `{ai_mode, ollama_reachable, whisper_available, translation_languages}` (non-blocking; languages appear once the translation engine has loaded)
- The ASHA app uses a two-step voice flow: `/transcribe` → ASHA confirms/corrects → `/triage/extract` with confirmed English `complaint_text` only. The gateway never forwards audio or language to extraction.

## Gateway / BFF (`apps/web/app/api/**`, Next.js route handlers)

Both client surfaces (ASHA PWA, Facility web) call only these routes; they
never call Core or AI directly (matches the architecture diagram).

- `POST /api/auth/login` → proxies Core
- `POST /api/patients`, `GET /api/patients/[abha]` → proxies Core
- `POST /api/encounters` → proxies Core
- `POST /api/triage/extract` → proxies AI service; on `503`/network error, returns `{ai_unavailable: true}` so the client falls back to the on-device checklist evaluator
- `POST /api/triage/transcribe`, `POST /api/triage/translate` → authenticated; validate language, audio format and size server-side; always 200 with either a result or a typed `transcription_unavailable` / `translation_unavailable` reason
- `GET /api/medicines`, `GET /api/medicines/[id]`, `GET /api/medicines/[id]/substitutes`, `POST /api/medicine-stock/[id]/link`, `POST /api/medication-orders`, `GET /api/medication-orders/[id]`, `GET /api/medication-orders/patient/[patientId]`, `POST /api/substitution-requests`, `GET /api/substitution-requests/facility/[facilityId]`, `POST /api/substitution-requests/[id]/approve`, `POST /api/substitution-requests/[id]/reject` → proxy Core (Core enforces roles and facility scope)
- `POST /api/triage` → proxies Core `/triage` (used for both the LLM path, after `/api/triage/extract`, and the offline checklist path where the client already computed severity on-device)
- `GET /api/queue/[facilityId]`, `GET /api/escalations/[facilityId]`, `POST /api/escalations/[id]/acknowledge`, `GET /api/dashboard/[facilityId]` → proxy Core
- `POST /api/patients/[abha]/verify-scheme` → proxies Core; facility-side only, never surfaced to the ASHA app
- `POST /api/referrals`, `GET /api/referrals/facility/[facilityId]`, `GET /api/referrals/patient/[patientId]`, `POST /api/referrals/[id]/status` → proxy Core
- `POST /api/diagnostics`, `GET /api/diagnostics/facility/[facilityId]`, `POST /api/diagnostics/[id]/status`, `POST /api/diagnostics/[id]/result` → proxy Core
- `POST /api/medicine-stock`, `GET /api/medicine-stock/facility/[facilityId]`, `POST /api/medicine-stock/[id]/adjust`, `GET /api/medicine-stock/[id]/movements` → proxy Core
- `POST /api/follow-ups`, `GET /api/follow-ups/facility/[facilityId]`, `GET /api/follow-ups/patient/[patientId]`, `POST /api/follow-ups/[id]/status` → proxy Core
- `POST /api/teleconsults`, `GET /api/teleconsults/facility/[facilityId]`, `POST /api/teleconsults/[id]/media`, `GET /api/teleconsults/[id]/media`, `POST /api/teleconsults/[id]/response` → proxy Core, including the real multipart file body

## Non-negotiables carried over from CLAUDE.md

- AI service never writes Postgres directly.
- Every triage decision, every severity, gets an `audit_log` row.
- Offline: the ASHA app's on-device TS rule evaluator over
  `rules/imnci-rules.v1.json` is the fallback — not a second, different rule
  set.
- No cloud LLM, no hosted vector DB, nothing in the offline critical path
  that requires connectivity.
- No mock features (2026-09-13 policy — see `CLAUDE.md`'s Non-negotiable
  rule and `docs/REAL-INTEGRATION-AUDIT.md`). `AbdmGatewayClient` and
  `NhaBeneficiaryClient` are real adapters built against the published
  ABDM/PM-JAY API shapes, behind the `AbdmClient`/`SchemeVerificationClient`
  interfaces in `services/core/app/adapters/`; both are honestly
  "not configured" until real NHA credentials are supplied via env vars —
  never fabricate a response in either adapter.
