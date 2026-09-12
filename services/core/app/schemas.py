import uuid
from datetime import datetime
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
    actor_user_id: uuid.UUID | None = None


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
