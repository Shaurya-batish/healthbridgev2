"""Imported medicine identities, facility stock link, medication orders and
doctor-authorised substitution requests.

- medicine_sources: provenance of every import (URL, licence, sha256, source
  version/date, price basis, counts).
- medicines + medicine_ingredients: structured identity (ingredient names,
  normalised strengths, form, route, release type, pack, price) and the
  fail-closed match_key from app/salt_matching.py.
- medicine_stock.medicine_id: links EXISTING facility inventory to an identity
  (no second stock system).
- medication_orders: versioned prescription lines, doctor-authored.
- substitution_requests: pending -> approved/rejected/invalidated, at most one
  pending request per order + proposed medicine (partial unique index).

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

medication_order_status = postgresql.ENUM("active", "superseded", "cancelled", name="medication_order_status", create_type=False)
substitution_request_status = postgresql.ENUM(
    "pending", "approved", "rejected", "invalidated", name="substitution_request_status", create_type=False
)


def _uuid_pk():
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _ts(name: str, nullable: bool = False, default: bool = True):
    return sa.Column(name, sa.TIMESTAMP(timezone=True), nullable=nullable, server_default=sa.func.now() if default else None)


def upgrade() -> None:
    bind = op.get_bind()
    medication_order_status.create(bind, checkfirst=True)
    substitution_request_status.create(bind, checkfirst=True)

    op.create_table(
        "medicine_sources",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("license", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("source_version", sa.Text(), nullable=True),
        sa.Column("source_updated_on", sa.Date(), nullable=True),
        sa.Column("price_basis", sa.Text(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matchable_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        _ts("imported_at"),
    )
    op.create_unique_constraint("uq_medicine_sources_name", "medicine_sources", ["name"])

    op.create_table(
        "medicines",
        _uuid_pk(),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medicine_sources.id"), nullable=False),
        sa.Column("source_record_id", sa.Text(), nullable=False),
        sa.Column("source_row_hash", sa.Text(), nullable=False),
        sa.Column("brand_name", sa.Text(), nullable=False),
        sa.Column("name_normalized", sa.Text(), nullable=False),
        sa.Column("generic_name", sa.Text(), nullable=True),
        sa.Column("manufacturer", sa.Text(), nullable=True),
        sa.Column("dosage_form", sa.Text(), nullable=True),
        sa.Column("route", sa.Text(), nullable=True),
        sa.Column("release_type", sa.Text(), nullable=False),
        sa.Column("pack_label", sa.Text(), nullable=True),
        sa.Column("pack_quantity", sa.Numeric(14, 4), nullable=True),
        sa.Column("pack_unit", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("unit_price", sa.Numeric(14, 4), nullable=True),
        sa.Column("is_discontinued", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("match_status", sa.Text(), nullable=False),
        sa.Column("match_key", sa.Text(), nullable=True),
        sa.Column("insufficient_reasons", sa.Text(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_unique_constraint("uq_medicines_source_record", "medicines", ["source_id", "source_record_id"])
    op.create_index("ix_medicines_match_key", "medicines", ["match_key"])
    op.create_index("ix_medicines_name_normalized", "medicines", ["name_normalized"])

    op.create_table(
        "medicine_ingredients",
        _uuid_pk(),
        sa.Column("medicine_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medicines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("strength_value", sa.Numeric(20, 8), nullable=True),
        sa.Column("strength_unit", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
    )
    op.create_index("ix_medicine_ingredients_name", "medicine_ingredients", ["name"])
    op.create_index("ix_medicine_ingredients_medicine_id", "medicine_ingredients", ["medicine_id"])

    op.add_column("medicine_stock", sa.Column("medicine_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_medicine_stock_medicine_id", "medicine_stock", "medicines", ["medicine_id"], ["id"])
    op.create_index("ix_medicine_stock_medicine_facility", "medicine_stock", ["medicine_id", "facility_id"])

    op.create_table(
        "medication_orders",
        _uuid_pk(),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("medicine_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medicines.id"), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("status", medication_order_status, nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medication_orders.id"), nullable=True),
        sa.Column("prescribed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index("ix_medication_orders_patient_id", "medication_orders", ["patient_id"])

    op.create_table(
        "substitution_requests",
        _uuid_pk(),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medication_orders.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("original_medicine_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medicines.id"), nullable=False),
        sa.Column("proposed_medicine_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medicines.id"), nullable=False),
        sa.Column("order_version", sa.Integer(), nullable=False),
        sa.Column("match_key_at_request", sa.Text(), nullable=False),
        sa.Column("status", substitution_request_status, nullable=False, server_default="pending"),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("resulting_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("medication_orders.id"), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index(
        "uq_substitution_requests_pending",
        "substitution_requests",
        ["order_id", "proposed_medicine_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_substitution_requests_facility_status", "substitution_requests", ["facility_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_substitution_requests_facility_status", table_name="substitution_requests")
    op.drop_index("uq_substitution_requests_pending", table_name="substitution_requests")
    op.drop_table("substitution_requests")
    op.drop_index("ix_medication_orders_patient_id", table_name="medication_orders")
    op.drop_table("medication_orders")
    op.drop_index("ix_medicine_stock_medicine_facility", table_name="medicine_stock")
    op.drop_constraint("fk_medicine_stock_medicine_id", "medicine_stock", type_="foreignkey")
    op.drop_column("medicine_stock", "medicine_id")
    op.drop_index("ix_medicine_ingredients_medicine_id", table_name="medicine_ingredients")
    op.drop_index("ix_medicine_ingredients_name", table_name="medicine_ingredients")
    op.drop_table("medicine_ingredients")
    op.drop_index("ix_medicines_name_normalized", table_name="medicines")
    op.drop_index("ix_medicines_match_key", table_name="medicines")
    op.drop_constraint("uq_medicines_source_record", "medicines", type_="unique")
    op.drop_table("medicines")
    op.drop_constraint("uq_medicine_sources_name", "medicine_sources", type_="unique")
    op.drop_table("medicine_sources")
    bind = op.get_bind()
    substitution_request_status.drop(bind, checkfirst=True)
    medication_order_status.drop(bind, checkfirst=True)
