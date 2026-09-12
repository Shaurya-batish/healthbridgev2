"""Sandbox-shaped ABDM client stand-in.

Deterministic: the same ABHA number always yields the same bundle, so demo
runs and tests are repeatable. Never calls out to the network -- the real
ABDM sandbox/production gateway is intentionally not on the critical path
(see CLAUDE.md top risks: "ABDM sandbox access is slow to obtain").
"""

import hashlib
import uuid

from app.adapters.abdm_client import AbdmClient

_FIRST_NAMES = ["Aarav", "Isha", "Vihaan", "Diya", "Kabir", "Anaya", "Reyansh", "Myra"]
_LAST_NAMES = ["Sharma", "Verma", "Patel", "Reddy", "Nair", "Singh", "Iyer", "Das"]
_GENDERS = ["male", "female"]
_STATES = ["Bihar", "Uttar Pradesh", "Madhya Pradesh", "Odisha", "Rajasthan"]


def _stable_int(seed: str, modulo: int) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest, 16) % modulo


def _stable_uuid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))


class MockAbdmClient:
    """Returns sandbox-shaped FHIR bundles for a given ABHA number.

    Implements `AbdmClient`. Swap this for a real gateway client later
    without touching any caller.
    """

    def fetch_patient_bundle(self, abha_number: str) -> dict:
        patient_id = _stable_uuid(f"abdm-patient:{abha_number}")
        name = f"{_FIRST_NAMES[_stable_int(abha_number + 'first', len(_FIRST_NAMES))]} " \
               f"{_LAST_NAMES[_stable_int(abha_number + 'last', len(_LAST_NAMES))]}"
        gender = _GENDERS[_stable_int(abha_number + 'gender', len(_GENDERS))]
        birth_year = 1960 + _stable_int(abha_number + 'year', 60)
        state = _STATES[_stable_int(abha_number + 'state', len(_STATES))]

        patient_resource = {
            "resourceType": "Patient",
            "id": patient_id,
            "identifier": [{"system": "https://healthid.ndhm.gov.in/abha", "value": abha_number}],
            "name": [{"text": name}],
            "gender": gender,
            "birthDate": f"{birth_year:04d}-01-01",
            "address": [{"state": state, "country": "IN"}],
        }

        return {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": 1,
            "entry": [{"resource": patient_resource}],
            "meta": {"source": "MockAbdmClient", "sandbox": True},
        }
