from fastapi import APIRouter

from app.db import db_reachable
from app.redis_client import redis_reachable
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", db_reachable=db_reachable(), redis_reachable=redis_reachable())
