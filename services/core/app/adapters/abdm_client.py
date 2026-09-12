"""The ABDM gateway seam.

Every caller in this codebase depends on this `AbdmClient` protocol, never on
a concrete class. `MockAbdmClient` is the only implementation today; a real
sandbox/production ABDM client is a swap-in behind this same interface, not
a rewrite of anything that calls it -- this is the adapter CLAUDE.md/
CONTRACT.md require for the live ABDM gateway module.
"""

from typing import Protocol


class AbdmClient(Protocol):
    def fetch_patient_bundle(self, abha_number: str) -> dict:
        """Return a FHIR Bundle for the given ABHA number."""
        ...
