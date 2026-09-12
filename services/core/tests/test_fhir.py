import uuid

from app.fhir import ABHA_IDENTIFIER_SYSTEM, build_encounter_resource, build_observation_resource, build_patient_resource


def test_patient_resource_uses_abha_identifier():
    patient_id = uuid.uuid4()
    resource = build_patient_resource(patient_id=patient_id, abha_number="12-3456-7890-1234", name="Test Patient", dob="2020-01-01", gender="female")

    assert resource["resourceType"] == "Patient"
    assert resource["id"] == str(patient_id)
    assert resource["identifier"][0] == {"system": ABHA_IDENTIFIER_SYSTEM, "value": "12-3456-7890-1234"}
    assert resource["gender"] == "female"


def test_encounter_resource_references_patient_and_facility():
    encounter_id, patient_id, facility_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    resource = build_encounter_resource(
        encounter_id=encounter_id,
        patient_id=patient_id,
        facility_id=facility_id,
        facility_level="phc",
        chief_complaint="fever and cough",
    )

    assert resource["subject"]["reference"] == f"Patient/{patient_id}"
    assert resource["serviceProvider"]["reference"] == f"Facility/{facility_id}"
    assert resource["reasonCode"][0]["text"] == "fever and cough"


def test_observation_resource_drops_none_facts_and_keeps_note():
    encounter_id = uuid.uuid4()
    resource = build_observation_resource(
        observation_id=uuid.uuid4(),
        encounter_id=encounter_id,
        extracted_facts={"fever_present": True, "stiff_neck": None},
        complaint_text="child has fever",
    )

    codes = [c["code"]["text"] for c in resource["component"]]
    assert codes == ["fever_present"]
    assert resource["note"][0]["text"] == "child has fever"
