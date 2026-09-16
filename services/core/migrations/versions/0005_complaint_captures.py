"""Multilingual complaint provenance.

One complaint_captures row per LLM-path triage decision: input source
(typed/voice), the ASHA-selected language, the first captured original text,
the machine translation and its engine, what the ASHA confirmed (original and
English, kept separately so a correction never overwrites the original),
confirmation/capture timestamps, recording consent, and -- for voice -- the
audio checksum/duration/format. Audio bytes are never stored server-side.

client_capture_id is unique so a replayed offline capture can never create a
second provenance row for the same recording.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

capture_input_source = postgresql.ENUM("typed", "voice", name="capture_input_source", create_type=False)
capture_translation_status = postgresql.ENUM("not_required", "machine", "manual", name="capture_translation_status", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    capture_input_source.create(bind, checkfirst=True)
    capture_translation_status.create(bind, checkfirst=True)

    op.create_table(
        "complaint_captures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("triage_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("triage_records.id"), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("captured_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("client_capture_id", sa.Text(), nullable=False),
        sa.Column("input_source", capture_input_source, nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("initial_machine_translation_en", sa.Text(), nullable=True),
        sa.Column("initial_translation_engine", sa.Text(), nullable=True),
        sa.Column("machine_translation_en", sa.Text(), nullable=True),
        sa.Column("translation_engine", sa.Text(), nullable=True),
        sa.Column("translation_status", capture_translation_status, nullable=False),
        sa.Column("confirmed_original_text", sa.Text(), nullable=False),
        sa.Column("confirmed_text_en", sa.Text(), nullable=False),
        sa.Column("original_edited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("english_edited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consent_confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("audio_sha256", sa.Text(), nullable=True),
        sa.Column("audio_duration_seconds", sa.Float(), nullable=True),
        sa.Column("audio_mime_type", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_complaint_captures_triage_record", "complaint_captures", ["triage_record_id"])
    op.create_unique_constraint("uq_complaint_captures_client_capture_id", "complaint_captures", ["client_capture_id"])
    op.create_index("ix_complaint_captures_encounter_id", "complaint_captures", ["encounter_id"])


def downgrade() -> None:
    op.drop_index("ix_complaint_captures_encounter_id", table_name="complaint_captures")
    op.drop_constraint("uq_complaint_captures_client_capture_id", "complaint_captures", type_="unique")
    op.drop_constraint("uq_complaint_captures_triage_record", "complaint_captures", type_="unique")
    op.drop_table("complaint_captures")
    bind = op.get_bind()
    capture_translation_status.drop(bind, checkfirst=True)
    capture_input_source.drop(bind, checkfirst=True)
