# HealthBridge AI service

FastAPI service, port 8100. Stateless — it never writes to Postgres. It
extracts structured facts from a complaint (text or voice) using a local
Phi-4-mini model via Ollama, then runs those facts through the versioned,
deterministic IMNCI rule table (`rules/imnci-rules.v1.json`, shared with the
ASHA app's on-device evaluator) to decide severity. **The LLM never decides
severity** — see `CONTRACT.md` at the repo root and `CLAUDE.md`'s "Triage
logic" section; that separation is load-bearing and must not be collapsed.

## Endpoints

- `POST /triage/extract` — `{complaint_text?, audio_base64?, age_months?}` →
  `{transcript?, extracted_facts, severity, rule_id, rule_version}`.
  Returns `503 {"detail": "ai_unavailable"}` if Ollama is unreachable, the
  model output can't be parsed as JSON, or (for audio input) Whisper isn't
  available — callers must treat all of these as "skip the LLM, use the
  on-device checklist," not as a hard failure.
- `POST /transcribe` — `{audio_base64, language, mime_type?}` →
  `{transcript, translation_en, language, engine, model, duration_seconds}`.
  Speech → original-language text (beam search, bounded temperature fallback)
  plus Whisper's English translation (default decoding). Never a severity.
  422 `invalid_audio`/`audio_too_short`/`audio_too_long`/`unsupported_audio_format`/
  `empty_transcript`; 503 `transcription_unavailable`. Recordings 0.5–120 s.
- `POST /translate` — `{text, source_language}` → `{translation_en, engine,
  engine_version}` for TYPED complaints, via local Argos Translate. 503
  `{code: translation_unavailable, reason}` when the language package isn't
  installed (Punjabi, Marathi and Tamil have none), the engine isn't installed,
  or `AI_MODE=degraded`.
- `GET /health` — `{ai_mode, ollama_reachable, whisper_available,
  translation_languages}`. Non-blocking: translation languages appear once the
  Argos engine has finished loading in the background.

The ASHA app never sends audio to `/triage/extract`: it calls `/transcribe`,
the ASHA confirms or corrects the text, and only the confirmed English is sent
for extraction.

## Local setup

```bash
cd services/ai
python -m venv .venv
. .venv/Scripts/activate        # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8100
```

### Ollama (required for live LLM extraction — not installed in this build sandbox)

```bash
# Install Ollama: https://ollama.com/download
ollama pull phi4-mini
ollama serve   # usually already running as a background service after install
```

Until Ollama is installed and the model pulled, `/triage/extract` with
`complaint_text` will return `503 ai_unavailable` — this is the intended
degradation path, not a bug.

### Whisper (required for the `audio_base64` path — not downloaded in this build sandbox)

`faster-whisper` is a real dependency in `requirements.txt` and the
transcription code path is fully implemented in `app/transcribe.py`, but the
model weights are lazy-loaded on first use and were **not** downloaded during
this build (multi-hundred-MB download, unnecessary for reviewing the code).
The first real call to the audio path will download the `small` Whisper
model automatically; to pre-fetch it:

```python
from faster_whisper import WhisperModel
WhisperModel("small", device="cpu", compute_type="int8")
```

Until then, `audio_base64` requests return `503 ai_unavailable`; `complaint_text`
requests are unaffected.

(2026-09-15: the `small` model was downloaded and run for real on Hindi and
Tamil speech; results and quality limits are in
`docs/MULTILINGUAL-VOICE-MEDICINES.md`.)

### Typed-text translation (Argos Translate, optional)

```bash
pip install argostranslate          # already in requirements.txt; pulls torch
python scripts/install_translation_packages.py   # hi->en and bn->en; needs internet once
# restart the service afterwards -- installed languages are read when the engine loads
```

`ARGOS_CHUNK_TYPE` defaults to `MINISBD` in `app/translate.py`: the published
Bengali package's bundled Stanza splitter crashes under stanza 1.10. MiniSBD
downloads a small sentence model on first use per language (Hindi: 178 KB);
Bengali has none and falls back to Argos' English splitter.

### Real-model checks (opt-in, not mocked)

```bash
HB_REAL_MODELS=1 HB_SPEECH_DIR=/path/to/fleurs/clips pytest tests/test_real_models.py -s
```

## Tests

```bash
cd services/ai
pytest
```

`tests/test_rules_engine.py` covers every rule id in
`rules/imnci-rules.v1.json` (all RED/YELLOW rules, the age-banded fast-breathing
thresholds, the "at least 2 of 4" dehydration rule, the GREEN default, and
missing-field safety). `tests/test_graph.py` and `tests/test_main.py` mock
the Ollama call (no live model needed) to verify the extract → sanitize →
evaluate pipeline, including that a hallucinated `severity`/`urgency` field
from the model is always stripped before it can reach a client.

## Design notes / deviations from CONTRACT.md

- None. Endpoints, ports, error shapes, and the rule-table contract are
  implemented exactly as specified.
- `coerce_to_fact_schema` validates each extracted field individually and
  drops only the fields that fail schema validation (e.g. a hallucinated
  enum value), rather than failing the entire extraction — this wasn't
  spelled out in `CONTRACT.md` but follows directly from its "never a raw
  stack trace" instruction for the transcription path, applied consistently.
- The rule table and fact schema are read from `rules/imnci-rules.v1.json`
  at runtime (cached after first load); nothing about the clinical rules is
  hardcoded in Python.
