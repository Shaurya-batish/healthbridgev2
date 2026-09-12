"""FHIR-shaped resource builders.

Intentionally minimal: enough structure (resourceType, identifiers, coded
fields) to demonstrate real FHIR shape and round-trip through JSONB, not a
full FHIR R4 validator. The ABHA number is always the Patient's primary
identifier -- it is the longitudinal key the whole architecture hangs off.
"""

import uuid
from datetime import datetime, timezone


ABHA_IDENTIFIER_SYSTEM = "https://healthid.ndhm.gov.in/abha"


def build_patient_resource(
    *,
    patient_id: uuid.UUID,
    abha_number: str,
    name: str,
    dob: str,
    gender: str,
) -> dict:
    return {
        "resourceType": "Patient",
        "id": str(patient_id),
        "identifier": [{"system": ABHA_IDENTIFIER_SYSTEM, "value": abha_number}],
        "name": [{"text": name}],
        "birthDate": dob,
        "gender": gender,
    }


def build_encounter_resource(
    *,
    encounter_id: uuid.UUID,
    patient_id: uuid.UUID,
    facility_id: uuid.UUID,
    facility_level: str,
    chief_complaint: str | None,
) -> dict:
    resource: dict = {
        "resourceType": "Encounter",
        "id": str(encounter_id),
        "status": "in-progress",
        "subject": {"reference": f"Patient/{patient_id}"},
        "serviceProvider": {"reference": f"Facility/{facility_id}"},
        "class": {"code": facility_level},
        "period": {"start": datetime.now(timezone.utc).isoformat()},
    }
    if chief_complaint:
        resource["reasonCode"] = [{"text": chief_complaint}]
    return resource


def build_observation_resource(
    *,
    observation_id: uuid.UUID,
    encounter_id: uuid.UUID,
    extracted_facts: dict,
    complaint_text: str | None,
) -> dict:
    components = [
        {"code": {"text": key}, "valueString": str(value)}
        for key, value in extracted_facts.items()
        if value is not None
    ]
    resource: dict = {
        "resourceType": "Observation",
        "id": str(observation_id),
        "status": "final",
        "encounter": {"reference": f"Encounter/{encounter_id}"},
        "effectiveDateTime": datetime.now(timezone.utc).isoformat(),
        "component": components,
    }
    if complaint_text:
        resource["note"] = [{"text": complaint_text}]
    return resource
