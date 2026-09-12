"""Lazy, optional Redis client.

Redis is used only for escalation pub/sub (per CONTRACT.md) -- Postgres
already owns queue-order truth, so there is no second queue implementation
here. Connection is lazy and every call is best-effort: a facility with
Redis down must still be able to save a RED escalation to Postgres, it just
won't get the live pub/sub notification.
"""

import json
from functools import lru_cache

import redis

from app.config import get_settings


@lru_cache
def get_redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=1)


def publish_escalation(facility_id: str, payload: dict) -> bool:
    try:
        client = get_redis_client()
        client.publish(f"escalations:{facility_id}", json.dumps(payload, default=str))
        return True
    except Exception:
        return False


def redis_reachable() -> bool:
    try:
        return bool(get_redis_client().ping())
    except Exception:
        return False
