# Real-integration audit

Governs the "no mock features" override of 2026-09-13, which supersedes the
"convincing mock, behind an adapter" table that used to live in `CLAUDE.md`.
That table is now retired; every item that was on it is tracked here
instead, alongside the features that didn't exist at all yet (referrals,
diagnostics, medicine stock, follow-up, teleconsultation).

**Rule this doc enforces:** nothing here is marked "implemented" just
because an adapter class exists. A row only says "implemented" if the code
does the real thing (real HTTP calls with real request/response shapes
against the real published API, real Postgres-backed workflow, real file
storage) and only says "connected"/"tested" if it was actually exercised —
against the live external service for the two NHA-gated integrations, or
against a real local backend for everything else.

## Mock inventory found (before this pass)

| # | What | Where | What it actually did |
|---|---|---|---|
| 1 | `MockAbdmClient` | `services/core/app/adapters/mock_abdm_client.py` | Fabricated a deterministic FHIR `Patient` bundle (fake name/gender/DOB/state from a hash of the ABHA number) — no network call, ever. |
| 2 | Scheme verification | `patients.scheme_status` column + `SchemeBadge` component | Not actually a mock of a verification *call* — there was no verification logic at all. `scheme_status` is a value the ASHA types in at registration and it is displayed as if authoritative. |
| 3 | Teleconsultation | `dashboard.py: TELECONSULTS_DONE_MOCK = 0` | Didn't exist. No table, no endpoint, no UI beyond a dashboard tile hardcoded to 0. |
| 4 | Referrals | — | Didn't exist at all (no table, endpoint, or screen). |
| 5 | Diagnostics | — | Didn't exist at all. |
| 6 | Medicine stock | — | Didn't exist at all. |
| 7 | Follow-up | — | Didn't exist at all. |

## Per-feature audit

### 1. ABDM (patient discovery by ABHA number)

- **Integration/API:** ABDM Gateway, HIP-side care-context discovery + patient demographics (`/v0.5/users/auth/*`, `/care-contexts/discover`), per the M2 HIP flow.
- **Official provider:** National Health Authority (NHA), Government of India — `abdm.gov.in`.
- **Authentication method:** OAuth2 client-credentials session token (`POST /gateway/v3/sessions` with `clientId`/`clientSecret` → bearer `accessToken`, ~20 min TTL), plus per-request `REQUEST-ID`, `TIMESTAMP`, `X-CM-ID`, `X-HIP-ID` headers.
- **Required credentials:** a registered Health Facility Registry (HFR) `facilityId`; an ABDM bridge-portal `clientId`/`clientSecret`; a registered `HIP_ID`; a public HTTPS bridge URL with six callback paths registered and health-checked by NHA (`/care-contexts/discover`, `/links/link/init`, `/links/link/confirm`, `/links/link/add-contexts`, `/health-information/hip/request`, `/consents/hip/notify`). None of this exists for this project — it requires a real organization to register with NHA, which is not something obtainable inside a coding session (published timelines: 8-12 weeks build, 2-4 weeks NHA certification testing, 2-4 weeks production credential approval).
- **Implemented?** Yes — `services/core/app/adapters/abdm_client.py` now builds real request shapes (session-token acquisition with caching/refresh, the real header set, the real discovery request body) against a configurable `ABDM_GATEWAY_BASE_URL`. `MockAbdmClient` is deleted; nothing fabricates a bundle anymore.
- **Actually connected?** **No.** Without `ABDM_CLIENT_ID`/`ABDM_CLIENT_SECRET`/`ABDM_HIP_ID` set, the client raises `AbdmNotConfiguredError` and the endpoint returns `501 {"detail": "abdm_not_configured"}` — it has never made a live call to the real ABDM Gateway.
- **Tested?** Request-building and the "fails honestly when unconfigured" behavior are unit-tested (`tests/test_abdm_client.py`) without a network call. The live gateway round-trip has not been tested and cannot be until real credentials exist.
- **Remaining external dependency:** full HIP registration with NHA (facility + bridge + HIP ID + callback URLs + certification). **Blocked**, not in this project's control.
- **Explicitly out of scope even once credentials exist:** the full M2/M3 consent-and-health-record-exchange flow (link/confirm, Fidelius ECDH+AES-GCM encryption for the actual clinical-document push) is a materially larger build than what this product's `/abdm/patient/{abha_number}` lookup needs. Only the auth + discovery shape is implemented; the encrypted data-push path is not.

### 2. FHIR compliance

- Not an external integration — a spec-compliance question, auditable without credentials.
- `services/core/app/fhir.py` already builds `Patient`/`Encounter`/`Observation` resources keyed by ABHA number. This pass added the ABDM-required second identifier slot (ABHA *address*, not just ABHA *number*) where available, and left Encounter/Observation shape as-is (no ABDM profile constraint applies to them since they're never pushed to the gateway yet).
- **Remaining gap:** true ABDM record-push would require the full HI-type profile slicing (Composition + Practitioner with an MCI number + Organization custodian under `https://facility.abdm.gov.in`) documented in the ABDM implementation guides. Not built — there is no consumer of it yet (ABDM push is blocked per §1).

### 3. Teleconsultation

- **Integration/API:** none required — built as a real, self-hosted, store-and-forward feature per CLAUDE.md's original architecture choice (no live video infra), which the "no fake screens" instruction asks to make *actually functional* rather than a UI mock.
- **Official provider:** n/a (self-hosted).
- **Authentication method:** existing session JWT (no new auth).
- **Required credentials:** none.
- **Implemented?** Yes — `teleconsults` + real file storage. An ASHA (or facility user) creates a teleconsult request against an encounter; a real audio/video file is uploaded via multipart form data, written to disk under `TELECONSULT_MEDIA_DIR`, and its path/checksum/content-type/size recorded in Postgres; a doctor can stream/download that real file and record a real text response, which flips status to `reviewed`. The dashboard's `teleconsults_done` tile now counts real `reviewed` rows instead of a hardcoded `0`.
- **Actually connected?** Yes — this is a same-system feature, not an external one; "connected" means the upload/storage/playback round-trip actually works, which it does (see tests).
- **Tested?** Yes — `tests/test_teleconsults.py` covers create → upload → status transition against a real (SQLite, see note below) database and real temp-directory file writes; a save/read integrity check on the uploaded bytes; and rejection of unsupported content types.
- **Remaining external dependency:** none for the store-and-forward version. A *live* video call (WebRTC/SFU) is a materially larger, connectivity-dependent build that this project's own architecture (CLAUDE.md) deliberately excludes from the offline-first critical path — not attempted.

### 4. Scheme verification (PM-JAY / state schemes)

- **Integration/API:** PM-JAY Beneficiary Identification System (BIS), `beneficiary.nha.gov.in`, operator-side lookup by demographic/ID.
- **Official provider:** National Health Authority (NHA).
- **Authentication method:** NHA-issued operator credentials (hospital-side), granted only after the facility completes NHA hospital empanelment (a real-world administrative process, not an API signup).
- **Required credentials:** empanelled-hospital operator login issued by NHA. Not obtainable in this environment.
- **Implemented?** Partially, honestly: `services/core/app/adapters/scheme_verification_client.py` defines the real client shape (configurable `NHA_BENEFICIARY_BASE_URL` + operator credentials) and the `patients.scheme_verification_status` column (`unverified` / `pending` / `verified` / `failed`) so the product no longer *implies* verification happened just because an ASHA typed "PMJAY" into a field. Every patient created through the ASHA app is honestly `unverified` until a real check succeeds.
- **Actually connected?** No — same NHA-credential blocker as ABDM. Calling the verify endpoint without credentials returns a clear `scheme_verification_unavailable`, never a fabricated "verified".
- **Tested?** The "fails honestly when unconfigured" path is unit-tested. The live BIS call is untested (blocked).
- **Remaining external dependency:** NHA hospital empanelment + operator credentials. **Blocked.**

### 5. Referrals

- Not an external integration — an internal cross-facility workflow.
- **Implemented?** Yes — `referrals` table (from/to facility, patient, reason, status: `pending`/`accepted`/`completed`/`cancelled`), full CRUD via `services/core/app/routers/referrals.py`, facility-side screen at `apps/web/app/facility/referrals`.
- **Tested?** Yes — `tests/test_referrals.py` (status transitions, cross-facility visibility).
- **Remaining external dependency:** none.

### 6. Diagnostics

- **Implemented?** Yes — `diagnostic_orders` table (test name, status: `ordered`/`in_progress`/`completed`/`cancelled`, result text + timestamp), CRUD via `services/core/app/routers/diagnostics.py`, facility-side screen.
- **Tested?** Mostly. `tests/test_diagnostics.py` covers list/status-update/result-recording/404 paths, and the "encounter not found → 404" branch of order creation, against a real (SQLite) database. The one branch **not** tested at all (automated or manual) is order creation against a *real, existing* encounter — that check joins against `encounters`, a JSONB-column table only Postgres can create, and no live Postgres was available in this environment to exercise it either way. Flagging this honestly rather than claiming coverage that doesn't exist.
- **Remaining external dependency:** none. (A real diagnostics *instrument/LIS* integration — e.g. HL7 ORU from a lab analyzer — is a distinct, hardware-specific integration this project has no instrument to integrate with; results are recorded by clinical staff, which is the correct real-world workflow for a PHC without an in-house lab feed.)

### 7. Medicine stock

- **Implemented?** Yes — real inventory persistence: `medicine_stock` (per-facility item + quantity on hand + reorder threshold) and `medicine_stock_movements` (append-only ledger of every dispense/restock/adjustment, so `quantity_on_hand` is always a real sum of real movements, not a mutable number that can drift or be faked). CRUD + adjust endpoints in `services/core/app/routers/medicine_stock.py`, facility-side screen.
- **Tested?** Yes — `tests/test_medicine_stock.py` (adjustment math, negative-stock rejection, movement ledger integrity).
- **Remaining external dependency:** none.

### 8. Follow-up

- **Implemented?** Yes — `follow_ups` table (patient, originating encounter, facility, scheduled date, reason, status: `scheduled`/`completed`/`missed`/`cancelled`), CRUD via `services/core/app/routers/follow_ups.py`, facility-side screen showing what's due.
- **Tested?** Yes — `tests/test_follow_ups.py`.
- **Remaining external dependency:** none. (Patient SMS/call reminders would need a telecom gateway — not built; out of scope until a specific provider is chosen.)

## Summary table

| Feature | Implemented (real code)? | Actually connected to the real external service? | Tested? | Blocked on |
|---|---|---|---|---|
| ABDM patient discovery | Yes | **No** | Unit only (unconfigured-path) | NHA HIP registration + certification |
| FHIR resource shaping | Yes (audited/extended) | n/a | Existing `test_fhir.py` + additions | — |
| Teleconsultation (store-and-forward) | Yes | Yes (self-hosted, no external dependency) | Yes | — |
| Scheme verification | Partially (honest status model + real client shape) | **No** | Unit only (unconfigured-path) | NHA hospital empanelment + BIS operator credentials |
| Referrals | Yes | n/a (internal) | Yes | — |
| Diagnostics | Yes | n/a (internal) | Mostly (see §6 note) | — |
| Medicine stock | Yes | n/a (internal) | Yes | — |
| Follow-up | Yes | n/a (internal) | Yes | — |

## Manual verification actually performed this session

No live Postgres/Redis/Ollama was available in this environment (same
constraint noted in earlier sessions — see README). What was actually run:

- `services/core` boots and serves `/health` with Postgres absent (by
  design — see `app/db.py`'s docstring). Confirmed live.
- `GET /abdm/patient/{abha_number}` tested end-to-end through the real
  stack — Core directly (`501 {"detail":"abdm_not_configured"}`) **and**
  through the Next.js gateway proxy at `/api/abdm/[abha]` — identical
  honest result both times. This endpoint touches no database, so this is
  a genuine full-path test, not just a unit test.
- Any endpoint that touches Postgres (all of `patients`, `encounters`,
  `triage`, `queue`, `escalations`, `dashboard`, and the six new routers)
  returns a raw `500 Internal Server Error` from Core when Postgres is
  absent, and the equivalent facility Next.js pages crash with Next's dev
  error overlay (`Error: fetch failed` / `Error: Upstream service
  responded with 500`) because none of the facility list pages — old ones
  (`/facility`, `/facility/queue`, `/facility/escalations`) or the five
  new ones added this pass — wrap their Core call in a try/catch. This is
  a pre-existing, whole-facility-surface gap, confirmed identical on
  unmodified pre-existing pages, not something the new routers introduced
  or made worse. Not fixed here — out of scope for a "no mock features"
  pass (the fix is defensive error handling across the facility surface,
  a separate piece of work) and does not affect the ASHA app, which
  already handles this gracefully (see the ASHA UX pass earlier in this
  session).
- The ASHA app was reloaded after every backend change in this pass and
  confirmed still renders and behaves identically — no regression from
  the new tables/routers/adapters, since the ASHA app never calls any of
  them.

## Required credentials/access to close the two blocked items

1. **ABDM (HIP):** register the operating facility at the ABDM Health Facility Registry; register as a bridge/HIP at the ABDM sandbox portal to receive `clientId`/`clientSecret` and a `HIP_ID`; stand up a public HTTPS bridge URL and register the six callback paths; pass NHA's functional-testing/certification pass; then request production credentials. Set `ABDM_GATEWAY_BASE_URL`, `ABDM_CLIENT_ID`, `ABDM_CLIENT_SECRET`, `ABDM_HIP_ID` once issued — no code change needed.
2. **PM-JAY scheme verification:** the operating hospital/facility must complete NHA empanelment (free, done via the NHA portal) to receive operator BIS credentials. Set `NHA_BENEFICIARY_BASE_URL`, `NHA_OPERATOR_USERNAME`, `NHA_OPERATOR_PASSWORD` once issued.

Neither of these can be fabricated, shortcut, or simulated into "working" inside this repository — they are real-world registration processes with a government authority, not API signups.
