import uuid
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

UserRole = Enum("asha", "doctor", "admin", name="user_role")
FacilityLevel = Enum("sub_centre", "phc", "district_hospital", name="facility_level")
SeverityLevel = Enum("RED", "YELLOW", "GREEN", name="severity_level")
TriageSource = Enum("llm", "checklist", name="triage_source")
TokenStatus = Enum("waiting", "in_progress", "done", name="token_status")
EscalationStatus = Enum("open", "acknowledged", "resolved", name="escalation_status")
SchemeStatus = Enum("PMJAY", "state", "none", name="scheme_status_enum")
# Honest verification state, distinct from the ASHA's self-reported
# `scheme_status` claim above -- see docs/REAL-INTEGRATION-AUDIT.md.
# Nothing is ever "verified" without a real NHA BIS call succeeding.
SchemeVerificationStatus = Enum("unverified", "pending", "verified", "failed", name="scheme_verification_status")
ReferralStatus = Enum("pending", "accepted", "completed", "cancelled", name="referral_status")
DiagnosticStatus = Enum("ordered", "in_progress", "completed", "cancelled", name="diagnostic_status")
StockMovementReason = Enum("restock", "dispensed", "adjustment", name="stock_movement_reason")
FollowUpStatus = Enum("scheduled", "completed", "missed", "cancelled", name="follow_up_status")
TeleconsultStatus = Enum("pending", "recorded", "reviewed", name="teleconsult_status")
CaptureInputSource = Enum("typed", "voice", name="capture_input_source")
# 'stale' is deliberately absent: a capture whose English no longer matches
# its corrected original is rejected before it can be stored.
CaptureTranslationStatus = Enum("not_required", "machine", "manual", name="capture_translation_status")
MedicationOrderStatus = Enum("active", "superseded", "cancelled", name="medication_order_status")
SubstitutionRequestStatus = Enum("pending", "approved", "rejected", "invalidated", name="substitution_request_status")

SEVERITY_RANK = {"RED": 0, "YELLOW": 1, "GREEN": 2}


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(FacilityLevel, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(UserRole, nullable=False)
    facility_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = _uuid_pk()
    abha_number: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    scheme_status: Mapped[str] = mapped_column(SchemeStatus, nullable=False, default="none")
    # Honest by default: real verification only ever moves this away from
    # "unverified" via a successful NHA BIS call (see scheme_verification_client.py).
    scheme_verification_status: Mapped[str] = mapped_column(
        SchemeVerificationStatus, nullable=False, default="unverified"
    )
    fhir: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    encounters: Mapped[list["Encounter"]] = relationship(back_populates="patient")


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False)
    fhir: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    patient: Mapped["Patient"] = relationship(back_populates="encounters")


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False
    )
    fhir: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class QueueToken(Base):
    __tablename__ = "queue_tokens"
    # Defense in depth alongside the FOR UPDATE lock in
    # routers/encounters.py: even if some future code path allocates a
    # token number without taking that lock, the DB itself refuses two
    # tokens with the same number at the same facility.
    __table_args__ = (UniqueConstraint("facility_id", "token_number", name="uq_queue_tokens_facility_token_number"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False)
    token_number: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(SeverityLevel, nullable=False)
    status: Mapped[str] = mapped_column(TokenStatus, nullable=False, default="waiting")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class TriageRecord(Base):
    __tablename__ = "triage_records"

    id: Mapped[uuid.UUID] = _uuid_pk()
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False
    )
    complaint_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_facts: Mapped[dict] = mapped_column(JSONB, nullable=False)
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    rule_version: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(SeverityLevel, nullable=False)
    source: Mapped[str] = mapped_column(TriageSource, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class EscalationEvent(Base):
    __tablename__ = "escalation_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    triage_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("triage_records.id"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False)
    status: Mapped[str] = mapped_column(EscalationStatus, nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = _uuid_pk()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # JSONB in Postgres (unchanged schema); plain JSON only when the router
    # unit tests build this table on SQLite, so audited writes are testable.
    details: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# --- Real internal workflows added under the 2026-09-13 no-mock policy ---
# (referrals/diagnostics/medicine stock/follow-up/teleconsult). See
# docs/REAL-INTEGRATION-AUDIT.md. None of these need an external
# credential -- they are same-system operational data, same as
# queue_tokens/escalation_events above.


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False)
    from_facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False)
    to_facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(ReferralStatus, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class DiagnosticOrder(Base):
    __tablename__ = "diagnostic_orders"

    id: Mapped[uuid.UUID] = _uuid_pk()
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False)
    facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False)
    test_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(DiagnosticStatus, nullable=False, default="ordered")
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_recorded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class MedicineStock(Base):
    __tablename__ = "medicine_stock"

    id: Mapped[uuid.UUID] = _uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False)
    medicine_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Links this facility's real inventory row to an imported medicine
    # identity, so same-composition comparison can report actual stock.
    # Nullable: existing free-text stock rows stay valid and are simply
    # "unknown" to comparison until someone links them.
    medicine_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("medicines.id"), nullable=True)
    unit: Mapped[str] = mapped_column(Text, nullable=False, default="units")
    quantity_on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reorder_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class MedicineStockMovement(Base):
    """Append-only ledger. quantity_on_hand is always derivable as the sum
    of these -- a real audit trail, not a mutable counter that can drift
    or be silently overwritten."""

    __tablename__ = "medicine_stock_movements"

    id: Mapped[uuid.UUID] = _uuid_pk()
    stock_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("medicine_stock.id"), nullable=False)
    change_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(StockMovementReason, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False)
    facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False)
    scheduled_date: Mapped[date] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(FollowUpStatus, nullable=False, default="scheduled")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Teleconsult(Base):
    __tablename__ = "teleconsults"

    id: Mapped[uuid.UUID] = _uuid_pk()
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(TeleconsultStatus, nullable=False, default="pending")
    # Real store-and-forward media: a real uploaded file written to disk
    # under TELECONSULT_MEDIA_DIR, referenced here -- never a fake "call
    # completed" screen with no underlying artifact.
    media_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    media_checksum_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    doctor_response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class IdempotencyKey(Base):
    """Replay cache for the write endpoints an unreliable network can
    retry: POST /patients, /encounters, /triage. A client (in practice,
    the ASHA app's offline queue -- see apps/web/lib/offline-queue.ts)
    sends the same Idempotency-Key on every attempt of the same logical
    operation. response_body is a JSON string, not JSONB, deliberately --
    this keeps the table creatable on SQLite for tests, unlike
    patients/encounters/observations.
    """

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("idempotency_key", "endpoint", name="uq_idempotency_key_endpoint"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# --- Multilingual complaint provenance (migration 0005) ---


class ComplaintCapture(Base):
    """What the ASHA actually captured, in which language, how it became
    English, and what she confirmed -- written in the same transaction as the
    TriageRecord it explains. Originals are never overwritten: a correction
    lands in confirmed_original_text, the first capture stays in original_text.
    Audio itself is never stored server-side; only its checksum/duration."""

    __tablename__ = "complaint_captures"

    id: Mapped[uuid.UUID] = _uuid_pk()
    triage_record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("triage_records.id"), nullable=False, unique=True)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False)
    captured_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    client_capture_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    input_source: Mapped[str] = mapped_column(CaptureInputSource, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    # First machine translation ever produced for this capture (Whisper's for
    # voice), kept even if the ASHA later corrects the original and retranslates.
    initial_machine_translation_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    initial_translation_engine: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Latest machine translation (the one the confirmed English is compared to).
    machine_translation_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    translation_engine: Mapped[str | None] = mapped_column(Text, nullable=True)
    translation_status: Mapped[str] = mapped_column(CaptureTranslationStatus, nullable=False)
    confirmed_original_text: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed_text_en: Mapped[str] = mapped_column(Text, nullable=False)
    original_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    english_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consent_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    audio_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    audio_mime_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# --- Same-composition medicine comparison + doctor-authorised substitution
# (migration 0006). Imported reference data only -- see app/medicine_import.py.


class MedicineSource(Base):
    """One row per dataset. A re-import of a newer file updates sha256/version
    here and upserts its records, so medicine ids (referenced by stock and
    orders) stay stable across dataset versions."""

    __tablename__ = "medicine_sources"
    __table_args__ = (UniqueConstraint("name", name="uq_medicine_sources_name"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    license: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_updated_on: Mapped[date | None] = mapped_column(nullable=True)
    price_basis: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matchable_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Medicine(Base):
    __tablename__ = "medicines"
    __table_args__ = (
        UniqueConstraint("source_id", "source_record_id", name="uq_medicines_source_record"),
        Index("ix_medicines_match_key", "match_key"),
        Index("ix_medicines_name_normalized", "name_normalized"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("medicine_sources.id"), nullable=False)
    source_record_id: Mapped[str] = mapped_column(Text, nullable=False)
    # sha256 of the raw source row: an unchanged row is skipped on re-import.
    source_row_hash: Mapped[str] = mapped_column(Text, nullable=False)
    brand_name: Mapped[str] = mapped_column(Text, nullable=False)
    name_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    # Derived from the structured ingredients (the source has no generic-name column).
    generic_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(Text, nullable=True)
    dosage_form: Mapped[str | None] = mapped_column(Text, nullable=True)
    route: Mapped[str | None] = mapped_column(Text, nullable=True)
    release_type: Mapped[str] = mapped_column(Text, nullable=False)
    pack_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    pack_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    pack_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    is_discontinued: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    match_status: Mapped[str] = mapped_column(Text, nullable=False)
    match_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    insufficient_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    ingredients: Mapped[list["MedicineIngredient"]] = relationship(
        back_populates="medicine", order_by="MedicineIngredient.position", cascade="all, delete-orphan"
    )


class MedicineIngredient(Base):
    __tablename__ = "medicine_ingredients"
    __table_args__ = (Index("ix_medicine_ingredients_name", "name"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    medicine_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("medicines.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    strength_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    strength_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    medicine: Mapped["Medicine"] = relationship(back_populates="ingredients")


class MedicationOrder(Base):
    """A doctor's prescription line for a patient encounter. Never edited in
    place: a change supersedes the row and creates a new version, so what was
    prescribed, by whom and when is always reconstructable."""

    __tablename__ = "medication_orders"

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False)
    facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False)
    medicine_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("medicines.id"), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(MedicationOrderStatus, nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("medication_orders.id"), nullable=True)
    prescribed_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class SubstitutionRequest(Base):
    __tablename__ = "substitution_requests"
    __table_args__ = (
        # At most one open request per order + proposed medicine. Partial
        # index on both engines so the DB itself refuses a duplicate that
        # slipped past the application check under concurrency.
        Index(
            "uq_substitution_requests_pending",
            "order_id",
            "proposed_medicine_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("medication_orders.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False)
    facility_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("facilities.id"), nullable=False)
    original_medicine_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("medicines.id"), nullable=False)
    proposed_medicine_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("medicines.id"), nullable=False)
    order_version: Mapped[int] = mapped_column(Integer, nullable=False)
    match_key_at_request: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(SubstitutionRequestStatus, nullable=False, default="pending")
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    request_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resulting_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("medication_orders.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
