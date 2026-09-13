"""Real internal workflows + honest scheme-verification status.

Adds referrals, diagnostic_orders, medicine_stock (+ movements ledger),
follow_ups, teleconsults, and patients.scheme_verification_status. Part of
the 2026-09-13 "no mock features" policy -- see docs/REAL-INTEGRATION-AUDIT.md.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

scheme_verification_status = postgresql.ENUM(
    "unverified", "pending", "verified", "failed", name="scheme_verification_status"
)
referral_status = postgresql.ENUM("pending", "accepted", "completed", "cancelled", name="referral_status")
diagnostic_status = postgresql.ENUM("ordered", "in_progress", "completed", "cancelled", name="diagnostic_status")
stock_movement_reason = postgresql.ENUM("restock", "dispensed", "adjustment", name="stock_movement_reason")
follow_up_status = postgresql.ENUM("scheduled", "completed", "missed", "cancelled", name="follow_up_status")
teleconsult_status = postgresql.ENUM("pending", "recorded", "reviewed", name="teleconsult_status")


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (
        scheme_verification_status,
        referral_status,
        diagnostic_status,
        stock_movement_reason,
        follow_up_status,
        teleconsult_status,
    ):
        enum.create(bind, checkfirst=True)

    op.add_column(
        "patients",
        sa.Column(
            "scheme_verification_status",
            scheme_verification_status,
            nullable=False,
            server_default="unverified",
        ),
    )

    op.create_table(
        "referrals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("from_facility_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("to_facility_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", referral_status, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "diagnostic_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("test_name", sa.Text(), nullable=False),
        sa.Column("status", diagnostic_status, nullable=False, server_default="ordered"),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("result_recorded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "medicine_stock",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("medicine_name", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False, server_default="units"),
        sa.Column("quantity_on_hand", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reorder_threshold", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_medicine_stock_facility_name", "medicine_stock", ["facility_id", "medicine_name"])

    op.create_table(
        "medicine_stock_movements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("stock_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medicine_stock.id"), nullable=False),
        sa.Column("change_qty", sa.Integer(), nullable=False),
        sa.Column("reason", stock_movement_reason, nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "follow_ups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", follow_up_status, nullable=False, server_default="scheduled"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "teleconsults",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", teleconsult_status, nullable=False, server_default="pending"),
        sa.Column("media_path", sa.Text(), nullable=True),
        sa.Column("media_content_type", sa.Text(), nullable=True),
        sa.Column("media_size_bytes", sa.Integer(), nullable=True),
        sa.Column("media_checksum_sha256", sa.Text(), nullable=True),
        sa.Column("doctor_response_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("teleconsults")
    op.drop_table("follow_ups")
    op.drop_table("medicine_stock_movements")
    op.drop_constraint("uq_medicine_stock_facility_name", "medicine_stock", type_="unique")
    op.drop_table("medicine_stock")
    op.drop_table("diagnostic_orders")
    op.drop_table("referrals")
    op.drop_column("patients", "scheme_verification_status")

    bind = op.get_bind()
    for enum in (
        teleconsult_status,
        follow_up_status,
        stock_movement_reason,
        diagnostic_status,
        referral_status,
        scheme_verification_status,
    ):
        enum.drop(bind, checkfirst=True)
