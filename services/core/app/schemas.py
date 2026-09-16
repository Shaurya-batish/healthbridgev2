import uuid
from datetime import date, datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

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


CaptureLanguage = Literal["en", "hi", "pa", "bn", "mr", "ta"]
_MAX_COMPLAINT = 4000


class ComplaintCaptureIn(BaseModel):
    """Provenance of an LLM-path complaint. Every consistency rule that keeps
    the English sent to extraction honest is enforced here, server-side --
    the client UI enforcing the same thing is a convenience, not the control."""

    client_capture_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")
    input_source: Literal["typed", "voice"]
    language: CaptureLanguage
    original_text: str = Field(min_length=1, max_length=_MAX_COMPLAINT)
    # The first machine translation (e.g. Whisper's), preserved even after a
    # correction and retranslation replaced machine_translation_en.
    initial_machine_translation_en: str | None = Field(default=None, max_length=_MAX_COMPLAINT)
    initial_translation_engine: str | None = Field(default=None, max_length=120)
    machine_translation_en: str | None = Field(default=None, max_length=_MAX_COMPLAINT)
    translation_engine: str | None = Field(default=None, max_length=120)
    # 'stale' is accepted by the schema only so it can be rejected with a
    # specific, actionable error rather than a generic enum failure.
    translation_status: Literal["not_required", "machine", "manual", "stale"]
    confirmed_original_text: str = Field(min_length=1, max_length=_MAX_COMPLAINT)
    confirmed_text_en: str = Field(min_length=1, max_length=_MAX_COMPLAINT)
    captured_at: datetime
    confirmed_at: datetime
    consent_confirmed_at: datetime | None = None
    audio_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    audio_duration_seconds: float | None = Field(default=None, gt=0, le=600)
    audio_mime_type: str | None = Field(default=None, max_length=100)

    _no_blank = field_validator("original_text", "confirmed_original_text", "confirmed_text_en")(_reject_blank)

    @model_validator(mode="after")
    def _consistent(self) -> "ComplaintCaptureIn":
        if self.translation_status == "stale":
            raise ValueError("translation_stale_reconfirm_required")
        if bool(self.initial_machine_translation_en) != bool(self.initial_translation_engine):
            raise ValueError("initial_translation_requires_text_and_engine")
        if self.language == "en":
            if self.translation_status != "not_required":
                raise ValueError("english_capture_needs_no_translation")
            if self.confirmed_text_en.strip() != self.confirmed_original_text.strip():
                raise ValueError("english_capture_texts_must_match")
        else:
            if self.translation_status == "not_required":
                raise ValueError("non_english_capture_requires_translation")
            if self.translation_status == "machine":
                if not self.machine_translation_en or not self.translation_engine:
                    raise ValueError("machine_translation_requires_text_and_engine")
                if self.machine_translation_en.strip() != self.confirmed_text_en.strip():
                    raise ValueError("edited_translation_must_be_marked_manual")
        if self.input_source == "voice":
            if self.consent_confirmed_at is None:
                raise ValueError("voice_capture_requires_recording_consent")
            if not (self.audio_sha256 and self.audio_duration_seconds and self.audio_mime_type):
                raise ValueError("voice_capture_requires_audio_metadata")
        elif self.audio_sha256 or self.audio_duration_seconds or self.audio_mime_type or self.consent_confirmed_at:
            raise ValueError("typed_capture_must_not_carry_audio_metadata")
        if self.confirmed_at < self.captured_at:
            raise ValueError("confirmed_before_captured")
        return self


class ComplaintCaptureResponse(BaseModel):
    id: uuid.UUID
    input_source: str
    language: str
    original_text: str
    initial_machine_translation_en: str | None
    initial_translation_engine: str | None
    machine_translation_en: str | None
    translation_engine: str | None
    translation_status: str
    confirmed_original_text: str
    confirmed_text_en: str
    original_edited: bool
    english_edited: bool
    captured_at: datetime
    confirmed_at: datetime
    consent_confirmed_at: datetime | None
    audio_sha256: str | None
    audio_duration_seconds: float | None
    audio_mime_type: str | None


class TriageRequest(BaseModel):
    encounter_id: uuid.UUID
    complaint_text: str | None = Field(default=None, max_length=4000)
    source: Literal["llm", "checklist"]
    extracted_facts: dict = Field(default_factory=dict)
    severity: Severity
    rule_id: str = Field(min_length=1, max_length=64)
    rule_version: str = Field(min_length=1, max_length=32)
    # Present whenever the ASHA confirmed a typed/voice complaint -- on the LLM
    # path, and also on the checklist path when extraction was unavailable
    # after confirmation (the confirmed complaint is still clinical record).
    # Optional so ops queued offline by an older app build still sync.
    complaint_capture: ComplaintCaptureIn | None = None
    # No actor_user_id here -- a client-supplied actor would let anyone
    # attribute a triage decision to someone else in the audit log. The
    # router derives it from the authenticated session instead.

    @model_validator(mode="after")
    def _capture_matches_complaint(self) -> "TriageRequest":
        if self.complaint_capture is None:
            return self
        # The stored complaint (and, on the LLM path, the extraction input)
        # must be exactly the English the ASHA confirmed.
        if (self.complaint_text or "").strip() != self.complaint_capture.confirmed_text_en.strip():
            raise ValueError("complaint_text_must_equal_confirmed_english")
        return self


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
    complaint_capture: ComplaintCaptureResponse | None = None


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
    medicine_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class MedicineStockLinkRequest(BaseModel):
    # null unlinks the stock row from any imported medicine identity.
    medicine_id: uuid.UUID | None


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


class AiServiceUrlUpdateRequest(BaseModel):
    # Required but nullable: an explicit null clears the override and the
    # gateway falls back to its AI_SERVICE_URL env var.
    url: str | None = Field(max_length=500)

    @field_validator("url")
    @classmethod
    def _absolute_http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("must be an absolute http(s) URL")
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("must not contain credentials, a query string or a fragment")
        return value.rstrip("/")


class AiServiceUrlResponse(BaseModel):
    url: str | None
    redis_reachable: bool


class SchemeVerificationResponse(BaseModel):
    abha_number: str
    scheme_status: str
    scheme_verification_status: str


# --- Same-composition medicine comparison + substitution review ---
# Money and strengths are serialised as strings: they are Decimals in
# Postgres and a float round-trip must never change a displayed price.


class MedicineSourceInfo(BaseModel):
    name: str
    license: str
    source_url: str
    source_version: str | None
    source_updated_on: date | None
    imported_at: datetime


class MedicineIngredientResponse(BaseModel):
    name: str
    strength_value: str | None
    strength_unit: str | None
    raw_text: str


class MedicineSummary(BaseModel):
    id: uuid.UUID
    brand_name: str
    generic_name: str | None
    manufacturer: str | None
    dosage_form: str | None
    route: str | None
    release_type: str
    pack_label: str | None
    pack_quantity: str | None
    pack_unit: str | None
    price: str | None
    price_basis: str
    currency: str
    unit_price: str | None
    is_discontinued: bool
    match_status: str
    insufficient_reasons: list[str]
    ingredients: list[MedicineIngredientResponse]
    source: MedicineSourceInfo


class MedicineListResponse(BaseModel):
    items: list[MedicineSummary]
    total: int
    limit: int
    offset: int


class FacilityStockInfo(BaseModel):
    # available: linked stock with quantity > 0, counted recently
    # unavailable: linked stock counted recently at zero
    # stale: linked stock whose last recorded count is older than the threshold
    # unknown: this facility has no stock row linked to this medicine
    status: Literal["available", "unavailable", "stale", "unknown"]
    stock_id: uuid.UUID | None = None
    quantity_on_hand: int | None = None
    last_counted_at: datetime | None = None


class SubstituteCandidate(BaseModel):
    medicine: MedicineSummary
    stock: FacilityStockInfo
    price_comparable: bool
    saving_percent: int | None


class SubstitutesResponse(BaseModel):
    reference: MedicineSummary
    reference_stock: FacilityStockInfo
    facility_id: uuid.UUID
    comparable: bool
    not_comparable_reasons: list[str]
    # Ranked best-first and truncated; total_candidates is the full group size.
    candidates: list[SubstituteCandidate]
    total_candidates: int
    notice: str
    generated_at: datetime


class MedicationOrderCreateRequest(BaseModel):
    encounter_id: uuid.UUID
    medicine_id: uuid.UUID
    instructions: str = Field(min_length=1, max_length=1000)

    _no_blank = field_validator("instructions")(_reject_blank)


class MedicationOrderResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID
    facility_id: uuid.UUID
    medicine: MedicineSummary
    instructions: str
    status: str
    version: int
    supersedes_order_id: uuid.UUID | None
    prescribed_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SubstitutionRequestCreateRequest(BaseModel):
    order_id: uuid.UUID
    proposed_medicine_id: uuid.UUID
    note: str | None = Field(default=None, max_length=500)


class SubstitutionDecisionRequest(BaseModel):
    decision_note: str | None = Field(default=None, max_length=1000)


class SubstitutionRequestResponse(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    patient_id: uuid.UUID
    encounter_id: uuid.UUID
    facility_id: uuid.UUID
    original_medicine: MedicineSummary
    proposed_medicine: MedicineSummary
    order_version: int
    status: str
    requested_by_user_id: uuid.UUID
    request_note: str | None
    reviewed_by_user_id: uuid.UUID | None
    reviewed_at: datetime | None
    decision_note: str | None
    resulting_order_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
