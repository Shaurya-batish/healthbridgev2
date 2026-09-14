import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Severity = Literal["RED", "YELLOW", "GREEN"]

# Every free-text field below is length-capped and every identity field is
# rejected when blank. Before this, the API accepted a patient whose
# abha_number was "" or "   " -- and the ABHA number is the longitudinal key
# the entire data model hangs off (CLAUDE.md, §Data model) -- as well as
# arbitrarily long strings (a 200,000-character test_name was accepted and
# written straight to Postgres) and integers outside Postgres's INTEGER
# range, which surfaced as an unhandled 500. Limits are deliberately
# generous: they reject garbage, not real clinical input.
_MAX_QTY = 1_000_000


def _reject_blank(value: str) -> str:
    """Shared validator for fields that must carry actual content."""
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    token: str
    role: str
    facility_id: str | None


class PatientCreateRequest(BaseModel):
    abha_number: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    # Kept as a string (not date) so the FHIR Patient.birthDate value is
    # byte-identical to what the client sent, but it must actually be an
    # ISO calendar date -- "", "not-a-date" and "banana" were all accepted.
    dob: str = Field(min_length=10, max_length=10)
    # The ASHA app offers exactly female/male/other; "unknown" is kept
    # because FHIR defines it and a future intake form may need it.
    gender: Literal["female", "male", "other", "unknown"]
    scheme_status: Literal["PMJAY", "state", "none"] = "none"

    _no_blank = field_validator("abha_number", "name")(_reject_blank)

    @field_validator("dob")
    @classmethod
    def _valid_iso_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("must be an ISO date (YYYY-MM-DD)") from exc
        return value


class PatientResponse(BaseModel):
    id: uuid.UUID
    abha_number: str
    scheme_status: str
    scheme_verification_status: str
    fhir: dict
    created_at: datetime
    updated_at: datetime


class EncounterResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    facility_id: uuid.UUID
    fhir: dict
    created_at: datetime


class PatientDetailResponse(BaseModel):
    patient: PatientResponse
    encounters: list[EncounterResponse]


class EncounterCreateRequest(BaseModel):
    abha_number: str = Field(min_length=1, max_length=32)
    facility_id: uuid.UUID
    chief_complaint: str | None = Field(default=None, max_length=2000)

    _no_blank = field_validator("abha_number")(_reject_blank)


class TriageRequest(BaseModel):
    encounter_id: uuid.UUID
    complaint_text: str | None = Field(default=None, max_length=4000)
    source: Literal["llm", "checklist"]
    extracted_facts: dict = Field(default_factory=dict)
    severity: Severity
    rule_id: str = Field(min_length=1, max_length=64)
    rule_version: str = Field(min_length=1, max_length=32)
    # No actor_user_id here -- a client-supplied actor would let anyone
    # attribute a triage decision to someone else in the audit log. The
    # router derives it from the authenticated session instead.


class TriageRecordResponse(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    complaint_text: str | None
    extracted_facts: dict
    rule_id: str
    rule_version: str
    severity: str
    source: str
    created_at: datetime


class TriageResponse(BaseModel):
    triage_record: TriageRecordResponse
    queue_position: int
    escalation_created: bool


class QueueTokenResponse(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    facility_id: uuid.UUID
    token_number: int
    severity: str
    status: str
    created_at: datetime
    updated_at: datetime


class EscalationResponse(BaseModel):
    id: uuid.UUID
    triage_record_id: uuid.UUID
    patient_id: uuid.UUID
    facility_id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime


class DashboardResponse(BaseModel):
    triaged_by_severity: dict[str, int]
    queue_length: int
    teleconsults_done: int
    red_cases_escalated: int


class HealthResponse(BaseModel):
    status: str
    db_reachable: bool
    redis_reachable: bool


# --- Real internal workflows (2026-09-13 no-mock policy) ---

ReferralStatusT = Literal["pending", "accepted", "completed", "cancelled"]
DiagnosticStatusT = Literal["ordered", "in_progress", "completed", "cancelled"]
StockMovementReasonT = Literal["restock", "dispensed", "adjustment"]
FollowUpStatusT = Literal["scheduled", "completed", "missed", "cancelled"]
TeleconsultStatusT = Literal["pending", "recorded", "reviewed"]


class ReferralCreateRequest(BaseModel):
    patient_id: uuid.UUID
    encounter_id: uuid.UUID
    from_facility_id: uuid.UUID
    to_facility_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=1000)

    _no_blank = field_validator("reason")(_reject_blank)


class ReferralStatusUpdateRequest(BaseModel):
    status: ReferralStatusT


class ReferralResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID
    from_facility_id: uuid.UUID
    to_facility_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=1000)

    _no_blank = field_validator("reason")(_reject_blank)
    status: str
    created_at: datetime
    updated_at: datetime


class DiagnosticOrderCreateRequest(BaseModel):
    encounter_id: uuid.UUID
    facility_id: uuid.UUID
    test_name: str = Field(min_length=1, max_length=200)

    _no_blank = field_validator("test_name")(_reject_blank)


class DiagnosticStatusUpdateRequest(BaseModel):
    status: DiagnosticStatusT


class DiagnosticResultRequest(BaseModel):
    result_text: str = Field(min_length=1, max_length=5000)

    _no_blank = field_validator("result_text")(_reject_blank)


class DiagnosticOrderResponse(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    facility_id: uuid.UUID
    test_name: str
    status: str
    result_text: str | None
    result_recorded_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MedicineStockCreateRequest(BaseModel):
    facility_id: uuid.UUID
    medicine_name: str = Field(min_length=1, max_length=200)
    unit: str = Field(default="units", min_length=1, max_length=32)
    # A negative reorder threshold silently disables the low-stock warning
    # for that medicine forever, which is why it is rejected here.
    reorder_threshold: int = Field(default=0, ge=0, le=_MAX_QTY)
    # Deliberately no ge=0 here: create_medicine_stock() already rejects a
    # negative initial_quantity with a 400 and a domain-specific detail
    # ("initial_quantity_cannot_be_negative"), which its own test asserts.
    # A schema bound would pre-empt that with a generic 422 and change an
    # already-correct contract. Only the upper bound is added, to keep an
    # out-of-INTEGER-range value from reaching Postgres.
    initial_quantity: int = Field(default=0, le=_MAX_QTY)

    _no_blank = field_validator("medicine_name", "unit")(_reject_blank)


class MedicineStockAdjustRequest(BaseModel):
    # Bounded so a value outside Postgres's INTEGER range is a clean 422
    # instead of a NumericValueOutOfRange surfacing as an unhandled 500.
    change_qty: int = Field(ge=-_MAX_QTY, le=_MAX_QTY)
    reason: StockMovementReasonT
    # No actor_user_id here -- same reasoning as TriageRequest above.


class MedicineStockResponse(BaseModel):
    id: uuid.UUID
    facility_id: uuid.UUID
    medicine_name: str
    unit: str
    quantity_on_hand: int
    reorder_threshold: int
    created_at: datetime
    updated_at: datetime


class MedicineStockMovementResponse(BaseModel):
    id: uuid.UUID
    stock_id: uuid.UUID
    change_qty: int
    reason: str
    actor_user_id: uuid.UUID | None
    created_at: datetime


class FollowUpCreateRequest(BaseModel):
    patient_id: uuid.UUID
    encounter_id: uuid.UUID
    facility_id: uuid.UUID
    scheduled_date: date
    reason: str = Field(min_length=1, max_length=1000)

    _no_blank = field_validator("reason")(_reject_blank)


class FollowUpStatusUpdateRequest(BaseModel):
    status: FollowUpStatusT


class FollowUpResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID
    facility_id: uuid.UUID
    scheduled_date: date
    reason: str
    status: str
    created_at: datetime
    updated_at: datetime


class TeleconsultCreateRequest(BaseModel):
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    facility_id: uuid.UUID
    # No requested_by_user_id here -- derived from the authenticated
    # session, same reasoning as TriageRequest.actor_user_id above.


class TeleconsultResponseRequest(BaseModel):
    doctor_response_text: str = Field(min_length=1, max_length=5000)

    _no_blank = field_validator("doctor_response_text")(_reject_blank)


class TeleconsultResponse(BaseModel):
    id: uuid.UUID
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    facility_id: uuid.UUID
    requested_by_user_id: uuid.UUID | None
    status: str
    media_content_type: str | None
    media_size_bytes: int | None
    media_checksum_sha256: str | None
    doctor_response_text: str | None
    created_at: datetime
    updated_at: datetime


class SchemeVerificationResponse(BaseModel):
    abha_number: str
    scheme_status: str
    scheme_verification_status: str
