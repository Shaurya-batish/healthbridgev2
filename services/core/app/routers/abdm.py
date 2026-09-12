from fastapi import APIRouter

from app.adapters.abdm_client import AbdmClient
from app.adapters.mock_abdm_client import MockAbdmClient

router = APIRouter(prefix="/abdm", tags=["abdm"])

# The one place a concrete AbdmClient is instantiated. Swap this line for a
# real gateway client later -- every caller depends only on the protocol.
_client: AbdmClient = MockAbdmClient()


@router.get("/patient/{abha_number}")
def get_abdm_patient_bundle(abha_number: str) -> dict:
    return _client.fetch_patient_bundle(abha_number)
