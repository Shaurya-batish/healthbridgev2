"""Defense-in-depth unique constraint on (facility_id, token_number).

Fixes a real race condition found during the 2026-09-13 technical
hardening pass: two encounters created for the same facility at the same
instant could both read the same MAX(token_number) and both insert the
same token number. The application-level fix (SELECT ... FOR UPDATE on the
facility row, in routers/encounters.py) prevents this in the normal code
path; this constraint is the last line of defense at the DB level.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-13
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_queue_tokens_facility_token_number", "queue_tokens", ["facility_id", "token_number"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_queue_tokens_facility_token_number", "queue_tokens", type_="unique")
