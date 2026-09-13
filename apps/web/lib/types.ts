export type Severity = "RED" | "YELLOW" | "GREEN";

export type Role = "asha" | "doctor" | "admin";

export type SchemeStatus = "PMJAY" | "state" | "none";

export type TriageSource = "llm" | "checklist";

// Mirrors rules/imnci-rules.v1.json `fact_schema`. Keep in sync manually —
// the JSON is the source of truth, this type just gives editor/type safety
// over it on the TS side.
export interface ImnciFacts {
  age_months?: number | null;
  respiratory_rate_per_min?: number | null;
  unable_to_drink_or_feed?: boolean;
  vomits_everything?: boolean;
  convulsions?: boolean;
  lethargic_or_unconscious?: boolean;
  chest_indrawing?: boolean;
  stridor_when_calm?: boolean;
  cough_present?: boolean;
  diarrhea_present?: boolean;
  diarrhea_duration_days?: number | null;
  blood_in_stool?: boolean;
  restless_or_irritable?: boolean;
  sunken_eyes?: boolean;
  drinks_eagerly_thirsty?: boolean;
  skin_pinch_slow?: boolean;
  skin_pinch_very_slow?: boolean;
  fever_present?: boolean;
  fever_duration_days?: number | null;
  stiff_neck?: boolean;
  ear_pain?: boolean;
  ear_discharge?: boolean;
  tender_swelling_behind_ear?: boolean;
  visible_severe_wasting?: boolean;
  edema_both_feet?: boolean;
  palmar_pallor?: "none" | "some" | "severe" | null;
}

export interface TriageResult {
  severity: Severity;
  rule_id: string;
  rule_version: string;
  matched_description: string;
}

export interface FhirPatient {
  resourceType: "Patient";
  id?: string;
  identifier: Array<{ system: string; value: string }>;
  name?: Array<{ text: string }>;
  gender?: string;
  birthDate?: string;
  [key: string]: unknown;
}

export type SchemeVerificationStatus = "unverified" | "pending" | "verified" | "failed";

export interface Patient {
  id: string;
  abha_number: string;
  scheme_status: SchemeStatus;
  scheme_verification_status: SchemeVerificationStatus;
  fhir: FhirPatient;
  created_at: string;
  updated_at: string;
}

export interface Encounter {
  id: string;
  patient_id: string;
  facility_id: string;
  fhir: Record<string, unknown>;
  created_at: string;
}

export interface TriageRecord {
  id: string;
  encounter_id: string;
  complaint_text: string | null;
  extracted_facts: ImnciFacts;
  rule_id: string;
  rule_version: string;
  severity: Severity;
  source: TriageSource;
  created_at: string;
}

export interface QueueToken {
  id: string;
  encounter_id: string;
  facility_id: string;
  token_number: number;
  severity: Severity;
  status: "waiting" | "in_progress" | "done";
  created_at: string;
  updated_at: string;
}

export interface EscalationEvent {
  id: string;
  triage_record_id: string;
  patient_id: string;
  facility_id: string;
  status: "open" | "acknowledged" | "resolved";
  created_at: string;
  updated_at: string;
}

export interface DashboardTiles {
  triaged_by_severity: { RED: number; YELLOW: number; GREEN: number };
  queue_length: number;
  teleconsults_done: number;
  red_cases_escalated: number;
}

// --- Real internal workflows (2026-09-13 no-mock policy) ---

export type ReferralStatus = "pending" | "accepted" | "completed" | "cancelled";

export interface Referral {
  id: string;
  patient_id: string;
  encounter_id: string;
  from_facility_id: string;
  to_facility_id: string;
  reason: string;
  status: ReferralStatus;
  created_at: string;
  updated_at: string;
}

export type DiagnosticStatus = "ordered" | "in_progress" | "completed" | "cancelled";

export interface DiagnosticOrder {
  id: string;
  encounter_id: string;
  facility_id: string;
  test_name: string;
  status: DiagnosticStatus;
  result_text: string | null;
  result_recorded_at: string | null;
  created_at: string;
  updated_at: string;
}

export type StockMovementReason = "restock" | "dispensed" | "adjustment";

export interface MedicineStock {
  id: string;
  facility_id: string;
  medicine_name: string;
  unit: string;
  quantity_on_hand: number;
  reorder_threshold: number;
  created_at: string;
  updated_at: string;
}

export interface MedicineStockMovement {
  id: string;
  stock_id: string;
  change_qty: number;
  reason: StockMovementReason;
  actor_user_id: string | null;
  created_at: string;
}

export type FollowUpStatus = "scheduled" | "completed" | "missed" | "cancelled";

export interface FollowUp {
  id: string;
  patient_id: string;
  encounter_id: string;
  facility_id: string;
  scheduled_date: string;
  reason: string;
  status: FollowUpStatus;
  created_at: string;
  updated_at: string;
}

export type TeleconsultStatus = "pending" | "recorded" | "reviewed";

export interface Teleconsult {
  id: string;
  encounter_id: string;
  patient_id: string;
  facility_id: string;
  requested_by_user_id: string | null;
  status: TeleconsultStatus;
  media_content_type: string | null;
  media_size_bytes: number | null;
  media_checksum_sha256: string | null;
  doctor_response_text: string | null;
  created_at: string;
  updated_at: string;
}
