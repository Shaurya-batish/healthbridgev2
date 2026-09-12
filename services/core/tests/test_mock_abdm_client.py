from app.adapters.mock_abdm_client import MockAbdmClient


def test_same_abha_number_yields_identical_bundle():
    client = MockAbdmClient()
    a = client.fetch_patient_bundle("12-3456-7890-1234")
    b = client.fetch_patient_bundle("12-3456-7890-1234")
    assert a == b


def test_different_abha_numbers_yield_different_patients():
    client = MockAbdmClient()
    a = client.fetch_patient_bundle("11-1111-1111-1111")
    b = client.fetch_patient_bundle("22-2222-2222-2222")
    assert a["entry"][0]["resource"]["id"] != b["entry"][0]["resource"]["id"]


def test_bundle_is_fhir_shaped():
    client = MockAbdmClient()
    bundle = client.fetch_patient_bundle("33-3333-3333-3333")
    assert bundle["resourceType"] == "Bundle"
    resource = bundle["entry"][0]["resource"]
    assert resource["resourceType"] == "Patient"
    assert resource["identifier"][0]["value"] == "33-3333-3333-3333"
