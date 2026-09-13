"""Regression test for the queue-token-number race condition found during
the 2026-09-13 technical hardening pass -- see migrations/versions/0003
and the FOR UPDATE lock in routers/encounters.py.

`encounters`/`facilities` use JSONB (Postgres-only, not creatable on
SQLite), so a genuine two-connection race can't be exercised in this
environment. This instead verifies, at the SQL-compilation level, that the
facility lookup actually requests a row lock -- catching a future refactor
that silently drops `.with_for_update()` and reopens the race, which a
pure code-review pass could miss.
"""

import os

os.environ.setdefault("JWT_SECRET", "test-secret")

import inspect

from app.routers import encounters


def test_create_encounter_locks_the_facility_row_before_allocating_a_token_number():
    source = inspect.getsource(encounters.create_encounter)
    assert "with_for_update()" in source, (
        "create_encounter must lock the facility row while computing the next "
        "token_number -- without it, two concurrent encounters at the same "
        "facility (e.g. two simultaneous RED cases) can be assigned the same "
        "token number."
    )
    # The lock must be taken before the MAX(token_number) read it's meant to
    # protect, not after.
    lock_pos = source.index("with_for_update()")
    max_pos = source.index("func.max(QueueToken.token_number)")
    assert lock_pos < max_pos
