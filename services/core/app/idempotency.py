"""Idempotency-key replay cache for the write endpoints most exposed to
retries: POST /patients, /encounters, /triage. See docs/TECHNICAL-HARDENING-REPORT.md
("no idempotency key" remaining risk).

Contract: a client sends `Idempotency-Key: <uuid>` on a write. If Core
already has a stored response for that exact key *and* endpoint, it
replays that response verbatim instead of re-running the operation --
this is what turns "the client retried because it saw a timeout, but the
first request actually succeeded" from a duplicate write into a no-op.
The key is entirely client-generated (the ASHA app's offline queue reuses
its own per-operation UUID -- see apps/web/lib/offline-queue.ts) and
optional: omitting the header just means no replay protection for that
request, never an error.

The cached response is written in the SAME transaction as the operation
it protects (`record_idempotency` only calls `db.add`, never `db.commit`
-- callers commit once, after both the operation and its cache row are
staged) so the two can never diverge: either both land, or neither does.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IdempotencyKey

# Keys older than this are treated as expired -- a retry past this window
# is assumed to be a genuinely new attempt (e.g. the ASHA revisits a
# patient the next day and the app reuses a stale local id for some other
# reason), not a replay of the original request.
_TTL = timedelta(hours=24)


def check_idempotency(db: Session, key: str | None, endpoint: str) -> JSONResponse | None:
    """Returns the cached response for this key+endpoint if one exists and
    hasn't expired, else None (meaning: proceed with the operation normally)."""
    if not key:
        return None

    row = db.scalar(
        select(IdempotencyKey).where(IdempotencyKey.idempotency_key == key, IdempotencyKey.endpoint == endpoint)
    )
    if row is None:
        return None

    created_at = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created_at > _TTL:
        return None

    return JSONResponse(status_code=row.response_status, content=json.loads(row.response_body))


def record_idempotency(db: Session, key: str | None, endpoint: str, status_code: int, body: dict[str, Any]) -> None:
    """Stages the response for replay. Must be called after the operation's
    own db.flush() (so any server-generated fields in `body` are real) and
    BEFORE the caller's db.commit() -- never commits on its own."""
    if not key:
        return
    db.add(
        IdempotencyKey(
            idempotency_key=key,
            endpoint=endpoint,
            response_status=status_code,
            response_body=json.dumps(body),
        )
    )
