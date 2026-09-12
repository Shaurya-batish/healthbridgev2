from __future__ import annotations

from fastapi import FastAPI, HTTPException

from . import ollama_client, rules_engine, transcribe
from .graph import run_extraction
from .schemas import ExtractRequest, ExtractResponse, HealthResponse

app = FastAPI(title="HealthBridge AI service", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        ollama_reachable=ollama_client.is_reachable(),
        whisper_available=transcribe.is_available(),
    )


@app.post("/triage/extract", response_model=ExtractResponse)
def triage_extract(req: ExtractRequest) -> ExtractResponse:
    if not req.complaint_text and not req.audio_base64:
        raise HTTPException(status_code=400, detail="complaint_text or audio_base64 is required")

    transcript: str | None = None
    complaint_text = req.complaint_text

    if req.audio_base64:
        try:
            transcript = transcribe.transcribe_base64_audio(req.audio_base64)
        except transcribe.TranscriptionUnavailable as exc:
            raise HTTPException(status_code=503, detail="ai_unavailable") from exc
        complaint_text = transcript

    if not complaint_text:
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
        extracted_facts=extracted_facts,
        severity=decision["severity"],
        rule_id=decision["rule_id"],
        rule_version=decision["rule_version"],
    )
