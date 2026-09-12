# CLAUDE.md — HealthBridge

Permanent architecture and development rules for this repository. This file
governs how any agent (or human) works in this codebase. The source of truth
for architecture is `HealthBridge-Architecture.pdf` in the repo root — this
file is a working transcription of it for day-to-day dev use. **Do not invent
a different architecture.** If a change is needed, it starts with the spec,
not with code.

## Non-negotiable rule

Eight modules can't all be built for real in hackathon time — and shouldn't
be. One real vertical spine, demoed end to end, beats eight shallow ones.
Every mocked module sits behind an adapter interface so the mock is a
swap-in later, not a rewrite.

### Build real
- Patient record — FHIR-shaped, keyed by ABHA number
- Digital triage engine — LLM extraction + IMNCI rule table
- Severity-based queue + red-case auto-escalation
- Facility dashboard — 4 tiles, real system data only
- Offline-first ASHA app — PWA with local sync

### Convincing mock, behind an adapter
- Live ABDM gateway → `MockAbdmClient` returns sandbox-shaped FHIR bundles
- Teleconsult video → store-and-forward only, no live infra
- Scheme verification → a `scheme_status` badge, not an engine
- Referral, diagnostics, medicine stock, follow-up → data screens only

**Scope creep — a mock quietly becoming a "real" build — is the top project
risk.** This table is law. Under time pressure, cut in reverse order: mocks
first, offline second, the triage spine never.

## System architecture

Two client surfaces, one backend, split into a deterministic Core service and
a separate AI service — so a slow or offline model can never block a patient
record from saving.

```
ASHA field app (PWA, offline queue)      Facility web (doctor/admin)
              \                                /
               \-----> API gateway (Next.js BFF) <----/
                          /              \
                 Core service        AI service (FastAPI)
                 patients/queue/      Whisper -> Phi-4-mini -> rules
                 escalation                (returns severity only)
                    /      \
          MockAbdmClient  Postgres --- Redis
```

- Both clients talk **only** to the gateway.
- The gateway splits deterministic work (Core, always available) from AI
  work (degrades independently).
- **The AI service returns a severity label — it never writes the record
  itself.**

## Confirmed stack

Do not add back items that were explicitly cut (Qdrant, GPT-5.6 / any cloud
LLM in the critical path) — no vector-search use case exists for a
deterministic rule engine, and a cloud LLM breaks offline-first and raises
health-data compliance questions.

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS — one framework for both app surfaces and the BFF |
| Backend | FastAPI, Python, REST APIs — typed request/response models map onto structured triage output |
| Data | PostgreSQL (FHIR JSONB), Redis (priority queue + escalation pub/sub) — no semantic search in the critical path |
| AI | Phi-4-mini via Ollama, LangGraph, Whisper (local) — runs on modest PHC hardware with zero connectivity; cloud LLM stays optional, non-critical, online-only |

## Data model

Clinical data is stored as FHIR resources so "ABDM/FHIR interoperable" is
demonstrable, not a slide claim. Everything hangs off one key: **the ABHA
number**.

**FHIR resources (JSONB in Postgres):**
| Resource | Holds |
|---|---|
| Patient | Keyed by ABHA number — the longitudinal thread across facility levels |
| Encounter | One per visit: who, where, when, facility level |
| Observation | Symptoms and vitals captured at triage |

**Relational tables:** `users`, `facilities`, `queue_tokens`,
`triage_records`, `escalation_events`, `audit_log` — plus a single
`scheme_status` enum (`PMJAY` / `state` / `none`) on Patient.

## Triage logic — the part judges will poke hardest

**The LLM extracts facts. It never decides severity.** A versioned rule table
does that, and every decision is auditable. This separation is what makes
the triage defensible to a clinician, and it must never be collapsed (e.g.
by asking the LLM to also output a severity/urgency field).

Flow: `Complaint (free text/voice) -> LLM extract (facts only) -> Rule table
(IMNCI danger signs, versioned) -> RED / YELLOW / GREEN -> queue reorder (all
severities) + escalation event (RED only)`.

Every decision, whatever the color, is written to `audit_log` naming which
rule fired (input, extracted facts, rule id, severity).

### Offline degradation
If the AI service is unreachable, the LLM step is skipped entirely — the
ASHA fills a structured symptom checklist instead, and the **same** rule
table runs against it. The rule engine never depends on the model being
available.

## Offline-first ASHA app

Rural connectivity is intermittent by definition — an app that needs a live
connection fails the problem statement on sight.

- PWA with a local write queue (IndexedDB): register, triage, and token
  creation all work with zero signal.
- The rule table + matcher run on-device — a plain JSON table, no server
  round trip required for severity.
- Sync on reconnect: server timestamps win, encounters are append-only, so
  conflicts are rare by construction.

## Build order

Build the spine thin end-to-end first, then widen — never take one module to
100% while others sit at zero.

1. **Day 1 — Spine:** auth + roles, FHIR-shaped Patient record, create-patient
   flow on the ASHA app. Deploy immediately and keep it deployed.
2. **Day 1/2 — Triage:** LLM extract → rule engine → severity, matched rule
   shown in the UI. The centerpiece — give it the most polish.
3. **Day 2 — Queue & escalation:** severity-based token reorder; RED
   auto-fires an escalation event and notification.
4. **Day 2 — Dashboard:** four tiles from real data — triaged-by-severity,
   queue length, teleconsults done, red cases escalated.
5. **Day 2/3 — Offline:** ASHA flow works fully offline and syncs on
   reconnect. High demo payoff for the effort.
6. **Day 3 — Mocks & polish:** teleconsult store-and-forward, scheme badge,
   mock data screens, seeded demo patients, rehearsed script.

## Top risks

| Risk | Mitigation |
|---|---|
| Scope creep — mocks quietly become "real" builds | §Build-real/mock table is law; cut in reverse order under time pressure |
| Live demo fails on venue wifi | Recorded fallback video + seeded demo data; never demo cold on conference wifi |
| A clinician judge challenges the triage | LLM-extracts-only + visible matched rule + audit log, shown live |
| ABDM sandbox access is slow to obtain | Never on the critical path — `MockAbdmClient` from day one |
| Teleconsult video becomes a rabbit hole | Capped at store-and-forward; video is not the headline feature |

## Development rules

- Do not introduce a cloud LLM, hosted vector DB, or any dependency that
  requires connectivity into the critical (offline) path.
- Do not let the AI service write to Postgres directly — it returns a
  severity label to Core; Core owns all writes.
- Do not skip the audit log on any triage decision.
- Secrets, `.env` files, credentials, and generated/build artifacts must
  never be committed — see `.gitignore`.
- Prefer widening the thin spine over polishing one module to completion
  while others are untouched.
