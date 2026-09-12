# HealthBridge web (ASHA app + Facility web + BFF)

One Next.js App Router application, per `CLAUDE.md`, serving three roles:

- **ASHA field PWA** — `/asha/**`, offline-first (IndexedDB write queue, service worker).
- **Facility web** — `/facility/**`, doctor/admin dashboard, queue, escalations, patient search.
- **API gateway / BFF** — `/api/**`, the only thing either client talks to; proxies to the
  Core service (`CORE_SERVICE_URL`) and AI service (`AI_SERVICE_URL`). See `../../CONTRACT.md`.

## Setup

```bash
cp .env.example .env.local   # fill in JWT_SECRET (must match services/core), CORE/AI URLs
npm install
npm run dev                  # http://localhost:3000
```

`predev`/`prebuild` automatically copy `rules/imnci-rules.v1.json` (repo root) into
`lib/imnci-rules.v1.json` — that generated file is gitignored. Never hand-edit it; edit
the root JSON and re-run `npm run sync-rules` if you need it standalone.

Requires `services/core` (port 8000) and `services/ai` (port 8100) running for anything
beyond the login screen and static pages — see the repo root README for running the
full stack.

## Scripts

- `npm run dev` / `npm run build` / `npm run start`
- `npm run typecheck` — `tsc --noEmit`
- `npm test` — Vitest; covers every rule id in `rules/imnci-rules.v1.json` via `lib/rules-engine.test.ts`
- `npm run sync-rules` — re-copy the canonical rule table (run automatically by dev/build)

## Key implementation notes

- **`lib/rules-engine.ts`** is a from-scratch TypeScript implementation of the same
  condition grammar (`eq|neq|gt|gte|lt|lte|exists`, `all`/`any`/`atLeast`) that
  `services/ai`'s Python evaluator implements over the identical JSON file. This is what
  lets the ASHA app compute a real severity on-device when the AI service is unreachable,
  per `CLAUDE.md`'s offline-degradation rule — not a second, different rule set.
- **Offline queue** (`lib/offline-queue.ts`): patient registration queues straightforwardly.
  Encounter + triage submission is trickier because a triage record needs a server-assigned
  `encounter_id` — if the network drops between the two calls, the encounter is not
  re-sent; only the remaining triage half is re-queued against the now-known id.
- **Auth**: Core issues the JWT at `/auth/login`; this app only verifies it (`jose`,
  edge-compatible, used in both `middleware.ts` and Server Components) and stores it in
  an httpOnly cookie. It never mints its own tokens.
- **PWA**: `@ducanh2912/next-pwa` (maintained App Router-compatible fork of `next-pwa`),
  disabled in development so `next dev` isn't fighting a cached service worker.

## Deviations from `CONTRACT.md` (and why)

- Route groups are real path segments (`app/asha/**`, `app/facility/**`) rather than
  parenthesized route groups, since the login redirect needs actual `/asha` and
  `/facility` URLs.
- `app/api/escalations/[facilityId]/route.ts` was renamed to `app/api/escalations/[id]/route.ts`
  (semantically still a facility id) — Next.js requires one dynamic slug name per path
  position, and `.../[id]/acknowledge` already claims that segment.
- Added `GET /api/session`-equivalent logic inline (via `lib/server-session.ts`, server-only)
  rather than a new proxied endpoint — facility pages need `facility_id` from the session,
  not from Core, so this isn't a gateway route.
- Facility assignment for creating a token comes from the ASHA's own session
  (`facility_id` claim in the JWT), not a manual picker — `CONTRACT.md` doesn't define a
  facility-list endpoint, and an ASHA has exactly one home facility in this model.

## Validated in this sandbox

- `npm install`, `npx tsc --noEmit` — clean.
- `npm test` — 23/23 passing, one case per rule id plus edge cases (missing fields,
  multi-rule severity precedence, age-banded thresholds).
- `npm run build` — succeeds; all `/api/**` and session-dependent pages are correctly
  marked dynamic (ƒ) and did not attempt to call Core/AI at build time.

**Not validated here** (no Core/AI/Postgres/Redis running in this sandbox): live login,
end-to-end triage submission, dashboard/queue/escalation data, offline sync against a
real backend, or the service worker's actual offline behavior in a browser. Run the full
stack (repo root README) and exercise each flow manually before a demo.
