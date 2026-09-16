from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db import db_reachable
from app.redis_client import redis_reachable
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", db_reachable=db_reachable(), redis_reachable=redis_reachable())


@router.get("/ready")
def ready() -> JSONResponse:
    """Only route traffic when the database can serve patient operations.

    AI and Redis intentionally remain soft dependencies: their outage must
    not take patient records or manual rule-based triage offline.
    """
    available = db_reachable()
    return JSONResponse(
        {"status": "ready" if available else "not_ready"},
        status_code=200 if available else 503,
        headers={"Cache-Control": "no-store"},
    )
