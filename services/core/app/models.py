import uuid
from datetime import datetime, date

from sqlalchemy import (
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
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
    details: Mapped[dict] = mapped_column(JSONB, nullable=False)
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
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
