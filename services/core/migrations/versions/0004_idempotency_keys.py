"""Idempotency replay cache for POST /patients, /encounters, /triage.

Addresses a remaining risk from the 2026-09-13 technical hardening pass:
a network timeout where the server actually succeeded but the client
believes it failed can, on retry, produce a duplicate patient/encounter/
triage record. response_body is TEXT (a JSON string), not JSONB, so this
table stays creatable on SQLite for tests.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_idempotency_key_endpoint", "idempotency_keys", ["idempotency_key", "endpoint"])
    # Retrying a stale operation weeks later should behave like a fresh
    # one, not replay ancient state -- lookups should filter by recency in
    # application code; this index just makes that filter (and general
    # cache-row lookup) fast.
    op.create_index("ix_idempotency_keys_created_at", "idempotency_keys", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_created_at", table_name="idempotency_keys")
    op.drop_constraint("uq_idempotency_key_endpoint", "idempotency_keys", type_="unique")
    op.drop_table("idempotency_keys")
