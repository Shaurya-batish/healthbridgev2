from __future__ import annotations

import hmac

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import config, ollama_client, rules_engine, transcribe
from .graph import run_extraction
from .schemas import (
    ExtractRequest,
    ExtractResponse,
    HealthResponse,
    TranscribeRequest,
    TranscribeResponse,
)

app = FastAPI(title="HealthBridge AI service", version="0.1.0")


@app.middleware("http")
async def require_shared_secret(request: Request, call_next):
    # Only enforced when AI_SHARED_SECRET is set, i.e. when this service is
    # reachable from the public internet through a tunnel. /health stays open
    # so the gateway can report capability without holding the secret.
    secret = config.AI_SHARED_SECRET
    if secret and request.url.path != "/health":
        supplied = request.headers.get("X-AI-Key", "")
        if not hmac.compare_digest(supplied, secret):
            return JSONResponse(status_code=401, content={"detail": "invalid_ai_key"})
    return await call_next(request)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    # In degraded mode neither runtime exists on this host, so report false
    # without probing -- truthful, and no 2s Ollama timeout per health check.
    if config.is_degraded():
        return HealthResponse(ai_mode="degraded", ollama_reachable=False, whisper_available=False)
    return HealthResponse(
        ai_mode="local",
        ollama_reachable=ollama_client.is_reachable(),
        whisper_available=transcribe.is_available(),
    )


@app.post("/transcribe", response_model=TranscribeResponse)
def transcribe_audio(req: TranscribeRequest) -> TranscribeResponse:
    """Speech -> text only, never a severity. The ASHA app shows `transcript`
    (original language) as editable text, with `translation_en` beneath it;
    nothing reaches /triage/extract until a human has confirmed it."""
    try:
        original, english = transcribe.transcribe_and_translate(req.audio_base64, language=req.language)
    except transcribe.InvalidAudio as exc:
        raise HTTPException(status_code=422, detail="invalid_audio") from exc
    except transcribe.TranscriptionUnavailable as exc:
        raise HTTPException(status_code=503, detail="transcription_unavailable") from exc
    if not original or not english:
        raise HTTPException(status_code=422, detail="empty_transcript")
    return TranscribeResponse(transcript=original, translation_en=english, language=req.language)


@app.post("/triage/extract", response_model=ExtractResponse)
def triage_extract(req: ExtractRequest) -> ExtractResponse:
    if not req.complaint_text and not req.audio_base64:
        raise HTTPException(status_code=400, detail="complaint_text or audio_base64 is required")

    if config.is_degraded():
        raise HTTPException(status_code=503, detail="ai_unavailable")

    transcript: str | None = None
    translation_en: str | None = None
    complaint_text = req.complaint_text

    if req.audio_base64:
        try:
            transcript, translation_en = transcribe.transcribe_and_translate(req.audio_base64, language=req.language)
        except transcribe.InvalidAudio as exc:
            raise HTTPException(status_code=422, detail="invalid_audio") from exc
        except transcribe.TranscriptionUnavailable as exc:
            raise HTTPException(status_code=503, detail="ai_unavailable") from exc
        # Only English ever reaches the extraction prompt.
        complaint_text = translation_en

    if not complaint_text or not complaint_text.strip():
        raise HTTPException(status_code=400, detail="No complaint text available after transcription")

    try:
        extracted_facts = run_extraction(complaint_text=complaint_text, age_months=req.age_months)
    except ollama_client.OllamaUnavailable as exc:
        raise HTTPException(status_code=503, detail="ai_unavailable") from exc
    except ValueError as exc:
        # Model returned non-JSON output -- degrade the same way as "unreachable"
        # rather than surfacing a 500; the caller falls back to the checklist path.
        raise HTTPException(status_code=503, detail="ai_unavailable") from exc

    decision = rules_engine.evaluate(extracted_facts)

    return ExtractResponse(
        transcript=transcript,
        translation_en=translation_en,
        extracted_facts=extracted_facts,
        severity=decision["severity"],
        rule_id=decision["rule_id"],
        rule_version=decision["rule_version"],
    )
