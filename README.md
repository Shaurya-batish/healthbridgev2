# HealthBridge

An offline-capable, ASHA-operated, ABDM/FHIR-linked record that follows a rural
patient across every level of the public health system — sub-centre, PHC,
district hospital — with explainable danger-sign triage that reorders the
queue and escalates emergencies.

Built for the SIH problem statement on rural & underserved healthcare access.
Strengthens the public system; does not replace it.

**Status:** environment scaffold only — no application code yet. See
[`CLAUDE.md`](./CLAUDE.md) for the full architecture and the rules that
govern how this repo is built.

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

## Getting started

Application scaffolding (Next.js app, FastAPI services, docker-compose for
Postgres/Redis) has not been created yet. This will be added in a subsequent
pass following the build order above.

## Owner

Shaurya Batish
