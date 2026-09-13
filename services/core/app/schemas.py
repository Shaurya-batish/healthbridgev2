import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["RED", "YELLOW", "GREEN"]


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    role: str
    facility_id: str | None


class PatientCreateRequest(BaseModel):
    abha_number: str
    name: str
    dob: str
    gender: str
    scheme_status: Literal["PMJAY", "state", "none"] = "none"


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
    abha_number: str
    facility_id: uuid.UUID
    chief_complaint: str | None = None


class TriageRequest(BaseModel):
    encounter_id: uuid.UUID
    complaint_text: str | None = None
    source: Literal["llm", "checklist"]
    extracted_facts: dict = Field(default_factory=dict)
    severity: Severity
    rule_id: str
    rule_version: str
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
    reason: str


class ReferralStatusUpdateRequest(BaseModel):
    status: ReferralStatusT


class ReferralResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID
    from_facility_id: uuid.UUID
    to_facility_id: uuid.UUID
    reason: str
    status: str
    created_at: datetime
    updated_at: datetime


class DiagnosticOrderCreateRequest(BaseModel):
    encounter_id: uuid.UUID
    facility_id: uuid.UUID
    test_name: str


class DiagnosticStatusUpdateRequest(BaseModel):
    status: DiagnosticStatusT


class DiagnosticResultRequest(BaseModel):
    result_text: str


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
    medicine_name: str
    unit: str = "units"
    reorder_threshold: int = 0
    initial_quantity: int = 0


class MedicineStockAdjustRequest(BaseModel):
    change_qty: int
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
    reason: str


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
    doctor_response_text: str


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
