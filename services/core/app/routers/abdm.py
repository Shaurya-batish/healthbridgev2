from fastapi import APIRouter, HTTPException, status

from app.adapters.abdm_client import AbdmClient, AbdmGatewayClient, AbdmNotConfiguredError, AbdmUnavailableError

router = APIRouter(prefix="/abdm", tags=["abdm"])

# The one place a concrete AbdmClient is instantiated. Real client, no mock
# fallback -- see docs/REAL-INTEGRATION-AUDIT.md for why this is not yet
# actually connected to the live ABDM Gateway.
_client: AbdmClient = AbdmGatewayClient()


@router.get("/patient/{abha_number}")
def get_abdm_patient_bundle(abha_number: str) -> dict:
    try:
        return _client.fetch_patient_bundle(abha_number)
    except AbdmNotConfiguredError as exc:
        # Honest "not connected" signal -- never a fabricated bundle.
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="abdm_not_configured") from exc
    except AbdmUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="abdm_unavailable") from exc
