"""Runtime-settable configuration, held in Redis.

Only one key today: the AI service base URL. The AI service runs on a laptop
behind a Cloudflare quick tunnel whose public URL changes on every restart
(docs/DEPLOYMENT.md), so it must be repointable in seconds without
redeploying the gateway. The gateway reads this per request and falls back
to its own AI_SERVICE_URL env var when no override is set.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditLog
from app.redis_client import get_redis_client
from app.schemas import AiServiceUrlResponse, AiServiceUrlUpdateRequest
from app.security import CurrentUser, TokenPayload, require_role

router = APIRouter(prefix="/config", tags=["config"])

AI_SERVICE_URL_KEY = "config:ai_service_url"


@router.get("/ai-service-url", response_model=AiServiceUrlResponse)
def get_ai_service_url(current_user: CurrentUser) -> AiServiceUrlResponse:
    # Any signed-in role: the gateway reads this with the caller's own token
    # on the ASHA's triage requests. Redis down is not an error -- the
    # gateway just uses its env default.
    try:
        value = get_redis_client().get(AI_SERVICE_URL_KEY)
    except Exception:
        return AiServiceUrlResponse(url=None, redis_reachable=False)
    return AiServiceUrlResponse(url=value or None, redis_reachable=True)


@router.post("/ai-service-url", response_model=AiServiceUrlResponse)
def set_ai_service_url(
    payload: AiServiceUrlUpdateRequest,
    current_user: Annotated[TokenPayload, Depends(require_role("admin"))],
    db: Session = Depends(get_db),
) -> AiServiceUrlResponse:
    client = get_redis_client()
    try:
        previous = client.get(AI_SERVICE_URL_KEY)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="redis_unavailable") from exc

    # Audit row first and flushed (FK on actor is checked here), Redis write
    # second, commit last: a failed Redis write rolls the audit row back, so
    # the log never claims a change that didn't happen.
    db.add(
        AuditLog(
            actor_user_id=uuid.UUID(current_user.user_id),
            action="runtime_config_change",
            entity_type="runtime_config",
            entity_id=None,
            details={"key": AI_SERVICE_URL_KEY, "previous": previous, "new": payload.url},
        )
    )
    db.flush()
    try:
        if payload.url is None:
            client.delete(AI_SERVICE_URL_KEY)
        else:
            client.set(AI_SERVICE_URL_KEY, payload.url)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="redis_unavailable") from exc
    db.commit()
    return AiServiceUrlResponse(url=payload.url, redis_reachable=True)
