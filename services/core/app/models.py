import uuid
from datetime import datetime

from sqlalchemy import (
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
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
