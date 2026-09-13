import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Teleconsult
from app.schemas import TeleconsultCreateRequest, TeleconsultResponse, TeleconsultResponseRequest
from app.security import CurrentUser, require_facility_access

router = APIRouter(prefix="/teleconsults", tags=["teleconsults"])

# Real self-hosted store-and-forward -- no external video provider, per
# CLAUDE.md's original architecture choice. This is a genuinely functional
# feature (real file on disk, real checksum, real playback), not a UI mock
# of a video call. See docs/REAL-INTEGRATION-AUDIT.md.
_ALLOWED_CONTENT_TYPES = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "video/webm": ".webm",
    "video/mp4": ".mp4",
}
_UPLOAD_CHUNK_SIZE = 1024 * 1024


def _media_dir(teleconsult_id: uuid.UUID) -> Path:
    base = Path(get_settings().teleconsult_media_dir)
    directory = base / str(teleconsult_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@router.post("", response_model=TeleconsultResponse, status_code=status.HTTP_201_CREATED)
def create_teleconsult(payload: TeleconsultCreateRequest, current_user: CurrentUser, db: Session = Depends(get_db)) -> TeleconsultResponse:
    require_facility_access(current_user, payload.facility_id)
    teleconsult = Teleconsult(
        encounter_id=payload.encounter_id,
        patient_id=payload.patient_id,
        facility_id=payload.facility_id,
        requested_by_user_id=uuid.UUID(current_user.user_id),
    )
    db.add(teleconsult)
    db.commit()
    db.refresh(teleconsult)
    return TeleconsultResponse.model_validate(teleconsult, from_attributes=True)


@router.get("/facility/{facility_id}", response_model=list[TeleconsultResponse])
def list_teleconsults(facility_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> list[TeleconsultResponse]:
    require_facility_access(current_user, facility_id)
    items = db.scalars(
        select(Teleconsult).where(Teleconsult.facility_id == facility_id).order_by(Teleconsult.created_at.desc())
    ).all()
    return [TeleconsultResponse.model_validate(i, from_attributes=True) for i in items]


@router.post("/{teleconsult_id}/media", response_model=TeleconsultResponse)
async def upload_teleconsult_media(
    teleconsult_id: uuid.UUID, current_user: CurrentUser, file: UploadFile = File(...), db: Session = Depends(get_db)
) -> TeleconsultResponse:
    """Writes the REAL uploaded bytes to disk and records a real sha256
    checksum -- this is what "real" means for store-and-forward: an
    artifact a doctor can actually open and play, not a status flag."""
    teleconsult = db.get(Teleconsult, teleconsult_id)
    if teleconsult is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="teleconsult_not_found")
    require_facility_access(current_user, teleconsult.facility_id)

    content_type = file.content_type or ""
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported_media_type: {content_type or 'unknown'}",
        )

    max_bytes = get_settings().teleconsult_max_upload_bytes
    body = bytearray()
    while chunk := await file.read(_UPLOAD_CHUNK_SIZE):
        body.extend(chunk)
        if len(body) > max_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="upload_too_large")
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty_upload")

    # Filename is server-generated (never the client-supplied name) to rule
    # out path traversal / injection through the upload's filename field.
    extension = _ALLOWED_CONTENT_TYPES[content_type]
    destination = _media_dir(teleconsult.id) / f"recording{extension}"
    destination.write_bytes(body)

    teleconsult.media_path = str(destination)
    teleconsult.media_content_type = content_type
    teleconsult.media_size_bytes = len(body)
    teleconsult.media_checksum_sha256 = hashlib.sha256(body).hexdigest()
    teleconsult.status = "recorded"
    db.commit()
    db.refresh(teleconsult)
    return TeleconsultResponse.model_validate(teleconsult, from_attributes=True)


@router.get("/{teleconsult_id}/media")
def download_teleconsult_media(teleconsult_id: uuid.UUID, current_user: CurrentUser, db: Session = Depends(get_db)) -> FileResponse:
    teleconsult = db.get(Teleconsult, teleconsult_id)
    if teleconsult is None or not teleconsult.media_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="teleconsult_media_not_found")
    require_facility_access(current_user, teleconsult.facility_id)

    path = Path(teleconsult.media_path)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="teleconsult_media_missing_on_disk")

    return FileResponse(path, media_type=teleconsult.media_content_type or "application/octet-stream")


@router.post("/{teleconsult_id}/response", response_model=TeleconsultResponse)
def record_doctor_response(
    teleconsult_id: uuid.UUID, payload: TeleconsultResponseRequest, current_user: CurrentUser, db: Session = Depends(get_db)
) -> TeleconsultResponse:
    teleconsult = db.get(Teleconsult, teleconsult_id)
    if teleconsult is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="teleconsult_not_found")
    require_facility_access(current_user, teleconsult.facility_id)
    if teleconsult.status != "recorded":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="no_recording_to_respond_to")

    teleconsult.doctor_response_text = payload.doctor_response_text
    teleconsult.status = "reviewed"
    db.commit()
    db.refresh(teleconsult)
    return TeleconsultResponse.model_validate(teleconsult, from_attributes=True)
