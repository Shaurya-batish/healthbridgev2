# Multilingual capture, voice complaints and same-composition medicines

Team SYNAPSE · HealthbridgeV2 · implemented and verified 2026-09-15 on branch
`feat/multilingual-voice-medicines`.

This document is the honest record for three features: what was built, how to
set it up, what was verified against real dependencies, and what is still
limited or blocked. It follows `CLAUDE.md`'s no-mock rule and the triage
separation: **Whisper and the translation engine produce text only; Phi-4-mini
extracts facts; the versioned IMNCI rule table alone decides severity.**

## Status at a glance

| Feature | Implemented | Tested with mocks/fakes | Tested with real dependencies | Demo-ready |
|---|---|---|---|---|
| Multilingual capture | Yes | Yes | Partly: real Whisper (hi, ta), real Argos (hi, bn), real Postgres, real browser | **Partly.** Hindi works end to end. Clinical text is English-only, UI translations are unreviewed drafts, and typed translation exists only for hi/bn |
| Voice complaint capture | Yes | Yes | Yes: real Chrome MediaRecorder with a fake-mic audio fixture, gateway, real Whisper, IndexedDB, Postgres | **Partly.** Works end to end, but not tested with a physical microphone. Whisper `small` output is unreliable and must be reviewed |
| Same-salt comparison + substitution | Yes | Yes (synthetic fixture) | Yes: real licensed dataset in real Postgres, real UI/API, real row-lock concurrency | **Yes, as an informational workflow.** Source prices are not verified as current |

Not exercised anywhere: **Phi-4-mini extraction** (Ollama is not installed on
the build machine). Every voice/typed flow was completed through the
checklist fallback, which is the designed degradation path.

---

## 1. What was built

### Multilingual capture (`apps/web`, `services/ai`, `services/core`)

- **Language selection is explicit.** English, हिन्दी, ਪੰਜਾਬੀ, বাংলা, मराठी
  and தமிழ் appear in the triage form with native labels. The app language
  selector sits in the ASHA header. Nothing auto-detects language.
- **Typed complaints.** The ASHA types in the selected language. `POST
  /api/triage/translate` calls `POST /translate` on the AI service, which uses
  local Argos Translate. If no package exists for the language, the app says
  so and the ASHA types the English meaning herself, records voice, or uses
  the checklist.
- **Voice complaints.** `POST /api/triage/transcribe` calls `POST /transcribe`
  on the AI service. Whisper decodes the audio once and runs two passes:
  original language (beam search) and English (Whisper translate).
- **Review before extraction** (`components/asha/triage/ComplaintReview.tsx`,
  `lib/complaint-capture.ts`):
  - The original and English texts are both editable.
  - Editing the original marks the English **stale** and blocks confirmation
    until the ASHA retranslates or corrects the English.
  - Whisper's own quality signals (compression ratio, log-probability, script
    ratio) are shown as warnings. They never silently change the text.
- **Extraction input.** Only the confirmed English reaches `/triage/extract`.
  The gateway never forwards language or audio to extraction.
- **Provenance** is stored in `complaint_captures` in the same transaction as
  the triage record, and copied into the `triage_decision` audit row:
  - input source and language
  - the first captured text and the confirmed original
  - the first machine translation and engine, which are preserved after a
    retranslation, plus the latest machine translation and engine
  - the confirmed English, and edit flags derived server-side
  - capture, confirmation and consent timestamps
  - audio sha256, duration and format
- **Server-side enforcement.** Core rejects with 422 and writes nothing when:
  - the translation is stale;
  - English was edited but labelled machine;
  - a voice capture lacks consent or audio metadata;
  - `complaint_text` differs from the confirmed English.

  A replayed capture id gets 409.
- **Localization.** UI strings for the touched workflow live in
  `lib/i18n/messages/<lang>.json`. Clinical text (severity headings,
  instructions, rule explanations, checklist labels) is shown only from
  **reviewed** resources in `lib/i18n/clinical/`. None exist yet, so it stays
  canonical English with a visible notice. Rule ids and severities are never
  translated.

### Voice capture and offline queue

- **Recorder** (`lib/voice-recorder.ts`, `components/asha/triage/VoiceRecorderPanel.tsx`):
  - Uses real `getUserMedia` and `MediaRecorder`, with tap-to-start/stop,
    cancel and re-record controls. There is no press-and-hold, so it works
    with keyboard and touch.
  - Shows a live duration, limited to 1–120 s and 8 MB.
  - Reports denied permission, missing microphone, unsupported browser,
    insecure context, empty, too short, too long or too large distinctly.
  - Releases microphone tracks on stop, cancel, unmount and `pagehide`.
- **Server-side checks.** The gateway checks language, MIME allowlist and
  base64 size. The AI service decodes the audio and checks format and
  duration (0.5–120 s) before loading Whisper.
- **Offline queue** (`lib/voice-queue.ts`, `components/asha/PendingVoiceCaptures.tsx`),
  in IndexedDB `healthbridge-voice`:
  - **Binding.** Each recording is bound to the signed-in user id, facility,
    patient ABHA number, language, capture time, consent time and a `visitId`.
    The `visitId` becomes the encounter/triage Idempotency-Key, so a delayed
    capture can create only one encounter.
  - **States.** Recordings move through `pending_upload` → `transcribing` →
    `awaiting_confirmation` (or `failed`), then `completed`.
  - **Retries.** Up to 5 automatic attempts with backoff and a 120 s
    per-attempt timeout; manual retry is also available.
  - **Recovery.** A capture orphaned by a reload mid-upload is recovered once
    its lease (timeout + 15 s) expires. The list re-runs every 20 s, on
    reconnect, and on "Check now".
  - **Never auto-submitted.** A transcribed recording waits for the ASHA to
    open it. The review screen is locked to the recording's own patient, with
    a banner.
  - **Isolation.** Every read, write and delete is filtered by user id.
    **This is application-level separation, not encryption.** IndexedDB is
    readable by anyone with the unlocked device's browser profile.
  - **Retention.** Audio bytes are deleted as soon as transcription succeeds.
    Every capture is purged 72 h after recording, when deleted, or when its
    visit is saved. Audio is never stored on the server; only its hash and
    duration are.
- **Urgent cases never wait.** "Use Symptom Checklist Instead" is offered on
  every capture and review screen. Offline typed capture goes straight to the
  checklist.

### Same-composition comparison and doctor-authorised substitution

- **Data** (migration 0006):
  - `medicine_sources`: URL, licence, sha256, version, update date, price
    basis, counts.
  - `medicines` and `medicine_ingredients`: structured identity and a
    fail-closed `match_key`.
  - `medicine_stock.medicine_id`: links existing inventory to an identity. No
    second stock system was created.
  - `medication_orders`: versioned, doctor-authored prescriptions.
  - `substitution_requests`: status is `pending`, `approved`, `rejected` or
    `invalidated`, with a partial unique index allowing only one pending
    request per order and proposed medicine.
- **Matching** (`services/core/app/salt_matching.py`, rebuilt). Two products
  are comparable only if all of the following match exactly:
  - the complete ingredient set (exact names, so different chemical salts are
    not merged);
  - every normalised strength (mcg/mg/g → mg; mg per N mL → mg/mL; IU and
    "Million IU"; % only within w/w, w/v or v/v);
  - dosage form (a dispersible tablet ≠ a tablet; a softgel ≠ a capsule);
  - route (injections and bare "drops"/"solution" state no route and never
    match);
  - release type (SR ≠ ER ≠ not stated).

  "NA" strengths, spores/cells/LF units and discontinued products fail closed.
- **Pricing and ranking** (`services/core/app/medicine_comparison.py`):
  - Unit prices use the pack's own basis (per tablet/capsule, per mL, per g).
    A zero or missing pack size gives no unit price.
  - A saving is shown only for a strictly cheaper product priced on the same
    basis.
  - Stock is joined from real facility inventory and reported as
    `available`, `unavailable`, `stale` (last ledger count older than 30 days)
    or `unknown`.
  - The **whole** match group is ranked (available stock first, then
    comparable unit price) before the top 100 are returned with
    `total_candidates`.
- **Authorisation** (`routers/substitution_requests.py`, `routers/medication_orders.py`):
  - Only a `doctor` at the order's facility may prescribe, approve or reject;
    ASHAs and admins get 403 `clinician_role_required`.
  - Any user with facility access may *request* review. A request changes
    nothing.
  - Approval re-checks, under `SELECT … FOR UPDATE`, that the request is
    still pending, the prescription is the same active version, and the match
    still holds on current data. Otherwise the request becomes `invalidated`
    (409) and nothing is prescribed.
  - The prescription changes only through `supersede_order`, which marks the
    old order superseded and creates a new version authored by the approving
    doctor with identical instructions. There is no dose conversion and no
    automatic substitution.
  - Every step is audited.
- **UI.** Search and comparison at `/asha/medicines` and `/facility/medicines`,
  reachable from each active prescription on both patient pages. The review
  queue is at `/facility/substitutions`. The prescribe form is on the facility
  patient page (doctor only). The stock page has "Link to reference medicine".
  Every comparison says it is informational and needs clinician review.

---

## 2. Setup

### Database migrations

```bash
cd services/core
alembic upgrade head        # adds 0005 complaint_captures, 0006 medicines/orders/substitution
```

Migration 0001's `CREATE EXTENSION pgcrypto` is now conditional:
`gen_random_uuid()` is built into PostgreSQL 13+, and some PostgreSQL builds
don't ship contrib. Migrations 0005 and 0006 downgrade cleanly; the smoke test
checks upgrade, downgrade to 0004 and re-upgrade.

### Import the medicine dataset (real, licensed, never committed)

```bash
cd services/core
python scripts/import_medicines.py --download            # ~32 MB, sha256 verified before any row is read
# or: python scripts/import_medicines.py --csv /path/indian_medicine_data.csv
```

| Property | Value |
|---|---|
| Source | `junioralive/Indian-Medicine-Dataset`, MIT licence |
| URL | `https://raw.githubusercontent.com/junioralive/Indian-Medicine-Dataset/main/DATA/indian_medicine_data.csv` |
| sha256 | `c9de0182474f652b7790a85bf534d0df9bd814575fcbda7109696d0fb3bec042`, re-downloaded and verified 2026-09-15 |
| Version | git `45c86f98…` (last change to the CSV: 2024-01-30) |
| Price basis | not stated by the source ("price in ₹"), shown as such |
| Measured import | 253,973 rows, 0 rejected, 205,136 matchable, 11,944 match groups (6,459 with ≥2 products), 55 s |
| Measured re-import | 253,973 unchanged, 0 inserted/updated, 7.6 s |

A checksum mismatch or unexpected header aborts before anything is written.
Medicine ids stay stable across re-imports, so stock links and prescriptions
survive dataset updates.

### AI service: Whisper and translation

```bash
cd services/ai
pip install -r requirements.txt                    # faster-whisper, argostranslate (argostranslate pulls torch/stanza/spacy)
python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')"   # ~464 MB, once
python scripts/install_translation_packages.py     # hi->en and bn->en; reports pa/mr/ta as unavailable
# restart the AI service after installing translation packages
```

| Env var | Default | Notes |
|---|---|---|
| `WHISPER_MODEL` | `small` | `medium` could not be evaluated: its download stalled at 3 MB |
| `ARGOS_CHUNK_TYPE` | `MINISBD` (set in `app/translate.py`) | The Bengali package's bundled Stanza splitter crashes under stanza 1.10. MiniSBD downloads a small per-language model on first use (Hindi 178 KB); Bengali falls back to Argos' English splitter |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` (was `localhost`) | On Windows, `localhost` made the health probe take 4.25 s with Ollama absent, longer than the gateway's 3 s health timeout |

`/health` no longer blocks on loading Argos: it warms the engine in the
background and reports `translation_languages` once loaded.

### Tests and end-to-end run

```bash
# Core: SQLite + real PostgreSQL (DATABASE_URL server, or a throwaway pgserver instance)
cd services/core && pip install -r requirements-dev.txt && pytest
# AI unit/contract tests (fakes for model runtimes)
cd services/ai && pytest
# AI real-model checks (opt-in, NOT mocked)
HB_REAL_MODELS=1 HB_SPEECH_DIR=/path/to/fleurs/clips pytest tests/test_real_models.py -s
# Web
cd apps/web && npm test && npx tsc --noEmit && npx next lint
# Browser end-to-end against a running stack (web :3000, Core :8000, AI :8100, migrated+seeded+imported DB,
# plus a second ASHA "asha2" at the same facility for the isolation step)
E2E_AUDIO_WAV=/path/clip-48k.wav E2E_OUT=/tmp/e2e node e2e/voice-and-medicines.e2e.mjs
```

The end-to-end script drives the locally installed Chrome through
`playwright-core` (dev dependency). It feeds a WAV into **Chrome's fake
microphone**, which proves the real browser → gateway → Whisper → review →
save path but is **not** a physical-microphone test. Use a 48 kHz WAV; the
fake device loops the file, which produces repeated text.

---

## 3. Language support: what is verified

| Language | App UI strings | Clinical text | Voice (Whisper `small`) | Typed translation |
|---|---|---|---|---|
| English | Source | Canonical | Supported (no translation step) | Not needed |
| Hindi | Unreviewed draft | English + notice | **Verified for real**: FLEURS clips CER 0.17–0.32, correct script | **Verified for real** (Argos) |
| Tamil | Unreviewed draft | English + notice | **Verified for real** (transcript CER 0.08–0.31); English translation **not meaningful** | **Unavailable** (no Argos package) |
| Bengali | Unreviewed draft | English + notice | Not tested (no clip fetched) | **Verified for real** (Argos + MiniSBD) |
| Punjabi | Unreviewed draft | English + notice | Not tested | **Unavailable** (no Argos package) |
| Marathi | Unreviewed draft | English + notice | Not tested | **Unavailable** (no Argos package) |

Measured quality problems. This is why review is mandatory:
- **Hindi.** Whisper's English inverted a meaning ("walking half an hour is
  not a waste of time" → "There is no time to spend half an hour in Kutuhal
  village") and mangled a numeric sentence ("scored 71 points in 41 games").
- **Tamil.** English translations were garbled or hallucinated. With beam
  search on the translate pass they looped ("birds of the forest, …"), so that
  pass keeps Whisper's default decoding.
- **Browser (Opus) recordings.** Default decoding sometimes produced
  mixed-script or punctuation-only original text. Beam search with a bounded
  temperature fallback fixed most cases; the remaining degenerate output is
  flagged with a warning in the UI.
- **Argos.** Typed Hindi and Bengali produced meaningful English on the test
  sentences. Retranslating Whisper's imperfect Hindi transcript produced
  nonsense, as expected from a bad source.
- **Recommendation.** Evaluate a larger Whisper model (`medium`/`large-v3`)
  with authenticated downloads, and obtain native-speaker and clinician review
  of the UI and clinical strings before field use.

---

## 4. Verification performed (2026-09-15)

| Check | Result |
|---|---|
| Core `pytest` (SQLite routers + importer + matching, and real PostgreSQL 16 via pgserver: migrations, triage provenance, prescribing, substitution auth/state/concurrency) | **170 passed** |
| AI `pytest` (unit/contract, fakes for model runtimes) | **76 passed, 6 skipped** (opt-in real-model tests) |
| AI real-model tests (`HB_REAL_MODELS=1`, real Whisper `small` on 3 Hindi + 2 Tamil FLEURS clips, real Argos hi/bn, honest pa/mr/ta unavailability) | **10 passed** (final run). These check script, CER and English shape only; meaning was judged by reading the output (section 3) |
| Web `vitest` (capture/stale logic, recorder state machine with fake media, IndexedDB queue via fake-indexeddb, i18n resource integrity, gateway contract, formatting) | **96 passed**; `tsc` clean; `next lint` clean |
| Real dataset import + idempotent re-import into PostgreSQL | Passed (numbers in section 2) |
| Real comparison on imported data | Dolo 650 Tablet (₹34.27/15 = ₹2.2847/tablet): 513 exact matches, 90 cheaper in the first 100. Top: Alice 650mg at ₹0.331/tablet (85% lower). No dearer product shown as a saving; all candidates share the match key |
| Browser E2E (real Chrome, fake-mic fixture, real web/Core/AI/Postgres) | **Passed.** All 17 steps; details and database cross-check below |

The browser end-to-end steps, each verified in the UI and cross-checked in
Postgres:
1. Hindi recording → real Whisper → review screen, with the
   repetitive-transcript warning shown.
2. Editing the original blocks confirmation (stale).
3. Real Argos retranslation.
4. Save via the checklist fallback (no Ollama).
5. Offline recording queued in IndexedDB, bound to asha1 + patient +
   language.
6. asha2 on the same browser sees no recordings.
7. After reconnect, the queue uploads (it recovered an upload orphaned by a
   navigation) and waits for confirmation instead of auto-submitting.
8. The delayed capture opens locked to its own patient, then saves.
9. Microphone permission denial shows the message plus typed and checklist
   alternatives.
10. The doctor prescribes Dolo 650 from imported data.
11. Test stock is created (201) and linked (200) through the real API.
12. The ASHA comparison shows real facility stock.
13. The ASHA requests review.
14. ASHA approval returns **403 `clinician_role_required`**.
15. The doctor approves; the order is v1 superseded → v2 Alice 650mg active.

Database cross-check: one capture row per saved visit, with the initial
Whisper translation preserved separately from the Argos retranslation; no
duplicate encounters; the substitution audit trail present; queue still ordered
RED → YELLOW → GREEN.

Bugs found and fixed during verification:
- Comparison truncated to 100 **before** ranking, so an in-stock or cheaper
  product could be dropped.
- A navigation mid-upload left a capture stuck in `transcribing`, and nothing
  re-ran the queue afterwards.
- `/health` blocked on the Argos import.
- Bengali translation crashed in stanza.
- The first machine translation was overwritten on retranslation.
- Whisper temperature fallback produced garbage originals.
- The offline queue flush sent no Idempotency-Key when replaying operations.

---

## 5. Known limitations and blockers

- **Phi-4-mini extraction not exercised.** Ollama is not installed on this
  machine. Blocker: install Ollama and `ollama pull phi4-mini`.
- **No physical-microphone test.** Only Chrome's fake capture device was used.
  Needs a manual test on a real Android phone.
- **Whisper `small` quality is not clinically reliable**, especially the
  English translation and Tamil (section 3). A larger model was not evaluated:
  the download stalled.
- **Punjabi and Marathi voice** are untested. **Punjabi, Marathi and Tamil
  typed translation** are unavailable (no Argos packages). The app says so and
  requires ASHA-typed English.
- **Translations are unreviewed.** All non-English UI strings are unreviewed
  drafts, and there are no reviewed clinical translations, so clinical text is
  English with a notice.
- **Recordings on the phone are not encrypted.** User separation is
  application-level only.
- **Medicine data is informational only.** The source dataset's prices are
  not verified as current (some real rows look implausible) and the price
  basis is unstated. A matching composition does not establish
  interchangeability for a patient; the UI says so, and approval is
  doctor-only.
- **Release type is often unstated.** Products with no release marker match
  only other unmarked products; the clinician must confirm immediate vs
  modified release.
- **Legacy offline operations.** Triage operations queued offline by an older
  app build still sync without capture provenance. `complaint_capture` is
  optional for backward compatibility.
- **Pre-existing, not fixed.** Redis unavailable → escalation pub/sub is
  skipped (unchanged behaviour).

---

## 6. Demo walkthrough

Prerequisites: migrated and seeded database, the dataset imported, the AI
service running with Whisper (and Argos hi/bn), and the web app on
`localhost` (a secure context is required for the microphone). Log in as
`asha1 / asha-demo-pass`.

1. **Select Hindi and record.** Open a patient and choose *Start Visit*. Set
   *Caregiver's language* to हिन्दी, choose *Speak*, tick the consent box, then
   *Start recording*. Speak the complaint, then *Stop recording* and *Send for
   transcription*.
2. **Review, correct, confirm.** Check the Hindi original and the English. Fix
   a misheard word in the original: the English turns amber ("You changed the
   original…") and *Confirm* is disabled. Tap *Translate again*, or correct
   the English yourself, then *Confirm and check danger signs*.
3. **Rule-based triage.** With Ollama running, Phi-4-mini extracts facts and
   the rule table decides. Without it, the app says so and opens the
   checklist, which uses the same rules. Tick the signs, *See Result*, then
   *Confirm & Add to Queue*. The rule id and version are shown.
4. **Offline capture.** Start another visit, switch the phone to airplane
   mode, and record and send. You'll see "Saved on this phone for patient …"
   and can use the checklist immediately if the child may be seriously ill.
   Reconnect and go Home: *Recordings on this phone* shows *Transcribing*,
   then *Ready — needs your confirmation*.
5. **Delayed confirmation.** Tap *Review and confirm*. The banner names the
   patient and recording time, and the ABHA field is locked. Confirm and save
   as in steps 2–3.
6. **Real medicine search and stock.** Log in as `doctor1`, open the patient,
   and under *Prescribe* search "Dolo 650". Pick *Dolo 650 Tablet*, add
   instructions and save. Under *Medicine stock*, link an existing stock row to
   *Alice 650mg Tablet* with *Link to reference medicine*. Then, as `asha1`,
   open the patient and tap *Compare same-composition options*. You'll see
   per-tablet prices, "85% lower unit price", *In stock here*, and the
   informational notice.
7. **Request review.** Tap *Request doctor review* on a candidate. The
   prescription stays unchanged.
8. **Clinician enforcement.** An ASHA or admin calling `POST
   /api/substitution-requests/{id}/approve` gets 403
   `clinician_role_required`. Log in as `doctor1`, open *Substitutions*, and
   choose *Approve and update prescription*. The patient page now shows Dolo
   650 (v1) superseded and Alice 650mg (v2) active, and the audit log records
   the request, approval and supersession.
