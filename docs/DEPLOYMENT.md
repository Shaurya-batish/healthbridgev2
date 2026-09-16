# HealthBridge deployment handoff

Prepared 15 September 2026 from `feat/multilingual-voice-medicines`, commit
`4f4cfcfefe1d5947f3e12c423501bce27d867c50`. The deployment changes are on
`deploy/healthbridge-launch`. This handoff does not mean a site is live.

## What must be deployed

Use the existing architecture: Next.js gateway and both user interfaces,
FastAPI Core, PostgreSQL, Redis, and a separate local AI service. The gateway
is the only browser-facing service. AI failure continues to fall back to the
same on-device rule table. Do not replace the backend with browser storage,
fabricated responses, or an unrelated static website.

The selected feature branch contains voice recording, multilingual complaint
review, medicine search/comparison, prescriptions and clinician-approved
substitutions. `main` does not contain that complete feature set.

## Prepared hosting configuration

Railway configuration files are included for the two application services.
Select their absolute repository paths explicitly; a service's root directory
does not change where Railway searches for its configuration file. This follows
the [Railway monorepo guide](https://docs.railway.com/deployments/monorepo) and
[configuration reference](https://docs.railway.com/config-as-code/reference).

| Service | Root directory | Configuration file | Health check | Persistent storage |
|---|---|---|---|---|
| Web | `/` | `/infra/railway/web.toml` | `/login` | None |
| Core | `/services/core` | `/infra/railway/core.toml` | `/ready` | Mount `/data` |
| PostgreSQL | Managed database | Provider-managed | Provider-managed | Database volume |
| Redis | Managed Redis | Provider-managed | Provider-managed | Redis volume |

Web builds with repository-root context because its build copies `rules/`.
Core builds with `services/core` context. Core's Docker command runs
`alembic upgrade head` before starting the server. Keep one Core replica for
the initial demo with filesystem-backed recordings.

Create the services in the same project and environment. Their server-to-server
requests can use the provider's [private network](https://docs.railway.com/networking/private-networking).
Use actual returned service hostnames, ports and database variables rather than
guessing them. Verify Core is reachable from Web before exposing the Web URL.

### Runtime variables

| Service | Variable | Required value |
|---|---|---|
| Core | `DATABASE_URL` | PostgreSQL connection URL supplied by the database service |
| Core | `REDIS_URL` | Redis connection URL supplied by Redis |
| Core and Web | `JWT_SECRET` | The same randomly generated secret; replace the development default |
| Core | `TELECONSULT_MEDIA_DIR` | `/data/teleconsult-media`, on the mounted persistent volume |
| Core | `CORE_ALLOWED_ORIGINS` | The actual HTTPS Web origin |
| Core | `PORT` | Service port; Docker defaults to `8000` |
| Web | `CORE_SERVICE_URL` | Actual reachable Core base URL, without trailing slash |
| Web | `AI_SERVICE_URL` | Actual reachable AI base URL, without trailing slash |
| Web and AI | `AI_SHARED_SECRET` | The same separately generated secret when AI is tunnelled |
| AI | `AI_MODE` | `local` when Whisper/Ollama run; `degraded` explicitly disables models |
| AI | `OLLAMA_HOST` | Reachable Ollama address on the AI machine |
| AI | `OLLAMA_MODEL` | `phi4-mini` |
| AI | `WHISPER_MODEL` | `small`, the existing tested model choice |

Store secrets in the provider's environment-variable controls. They are never
client-side `NEXT_PUBLIC_*` values and must not be committed.

### First database setup

1. Wait for Core's migrations to finish and `/ready` to return 200.
2. Provision facilities and ASHA, doctor and admin accounts. The existing
   `scripts/seed_facilities_and_users.sql` is a **demo-only** seed with publicly
   documented passwords. Replace those passwords using Core's `hash_password`
   function before making the hosted demo reachable. Do not overwrite an
   existing deployment's users or patient records.
3. Import the real, checksum-verified catalogue from the Core container:

   ```bash
   python scripts/import_medicines.py --download --data-dir /data/medicine-sources
   ```

   The importer fails on checksum mismatch. Catalogue search remains empty
   until this completes; do not seed fictional medicine prices as a substitute.
4. Add only explicitly synthetic patient/demo records. The deployed database
   is a new instance; no laptop patient data has been copied.

### Connect the laptop AI service

Install the dependencies and model packages using
`docs/MULTILINGUAL-VOICE-MEDICINES.md`. Run Ollama with `phi4-mini` and run the
AI service on port 8100. A hosted gateway cannot reach `localhost` on a laptop:
it needs a reachable HTTPS tunnel endpoint. Configure `AI_SHARED_SECRET` on both
sides before exposing that endpoint. Keep the laptop and tunnel running.

Set the actual endpoint in Web's `AI_SERVICE_URL`. The existing authenticated
admin endpoint `POST /api/admin/ai-service-url` can replace the URL at runtime
if a temporary tunnel changes. Neither laptop access nor an AI tunnel has been
established in this session.

Without that connection, patient workflows and checklist triage remain useful,
but real Whisper transcription, local text translation and Phi-4 extraction
must not be presented as connected. Language support is partial: review the
per-language limitations in `docs/MULTILINGUAL-VOICE-MEDICINES.md`.

## Changes prepared for deployment

- Docker builds exclude secrets, local dependencies, model caches and local
  patient media from their build contexts.
- Web uses the committed lockfile through `npm ci`.
- Web tests and type checking synchronize the shared rule file automatically
  on a fresh checkout.
- Core `/ready` returns 503 if PostgreSQL is unreachable. AI and Redis stay
  optional for patient-record availability.
- PostgreSQL connections have a five-second connection timeout.
- Alembic accepts percent-encoded passwords in database URLs.
- Docker Compose preserves consultation recordings in a named volume.

## Verification in this session

| Check | Result |
|---|---|
| Feature-branch Next.js production build, lint/type checks | Passed |
| Web automated tests | 96 passed |
| Backend automated tests, including readiness behavior | 148 passed |
| Real PostgreSQL integration/migration tests | 24 setup errors: the local PostgreSQL helper could not create its required OS user in this execution environment |
| Railway TOML and Compose configuration parsing | Passed |
| Docker image builds | Not run: Docker is unavailable here |
| Full deployed browser workflow | Not run: hosting account is not connected |
| Real Whisper/Ollama inference in this session | Not run: no model runtime or laptop endpoint is connected |

The existing branch documents earlier real-model and database verification;
those historical results are not a new verification of this deployment.

## Publication gate and remaining limitations

Publishing requires an authorised Railway account to create the services and
GitHub write access to publish this deployment branch. A published branch alone
does not indicate a live deployment. No hosted infrastructure has been created
as part of this preparation.

The draft deployment PR runs `.github/workflows/deployment-checks.yml` with a
real PostgreSQL 16 service for the complete Core test suite and Docker builds
for both services. Its temporary credentials are CI-only. The workflow has no
deployment secrets and cannot publish the app. Check its actual result before
treating the previously blocked integration and container checks as verified.

After connecting, finish the real PostgreSQL checks, build the images, set up
accounts/catalogue/media storage, connect AI, and verify the HTTPS flows:
ASHA login -> patient registration -> reviewed complaint/checklist -> queue ->
doctor review; real media upload/playback; medicine search and doctor-only
substitution approval; reconnect/retry behavior. Confirm records and media
survive a restart before reporting a working deployed URL.

ABDM and scheme verification remain dependent on NHA credentials. The seed
still attaches the ASHA and doctor to the same PHC as a documented demo
workaround; ancestor-facility access is not implemented on this branch.
Do not claim a cross-level clinical rollout or full offline read support.
