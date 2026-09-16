"""Seeds real facility/user/patient/encounter rows in the migrated Postgres
test database (JSONB tables included) so router tests exercise real FKs."""
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.fhir import build_encounter_resource, build_patient_resource
from app.models import Encounter, Facility, Patient, QueueToken, User
from app.security import create_access_token


@dataclass
class World:
    facility_a: uuid.UUID
    facility_b: uuid.UUID
    asha_a: uuid.UUID
    doctor_a: uuid.UUID
    doctor_b: uuid.UUID
    admin: uuid.UUID
    patient: uuid.UUID
    encounter: uuid.UUID

    def headers(self, user: str) -> dict[str, str]:
        role, facility = {
            "asha_a": ("asha", self.facility_a),
            "doctor_a": ("doctor", self.facility_a),
            "doctor_b": ("doctor", self.facility_b),
            "admin": ("admin", None),
        }[user]
        return {"Authorization": f"Bearer {create_access_token(getattr(self, user), role, facility)}"}


def new_encounter(db: Session, patient_id: uuid.UUID, facility_id: uuid.UUID, token_number: int) -> uuid.UUID:
    encounter_id = uuid.uuid4()
    db.add(
        Encounter(
            id=encounter_id,
            patient_id=patient_id,
            facility_id=facility_id,
            fhir=build_encounter_resource(
                encounter_id=encounter_id, patient_id=patient_id, facility_id=facility_id, facility_level="phc", chief_complaint=None
            ),
        )
    )
    db.flush()
    db.add(QueueToken(encounter_id=encounter_id, facility_id=facility_id, token_number=token_number, severity="GREEN", status="waiting"))
    db.flush()
    return encounter_id


def seed_world(db: Session) -> World:
    fa, fb = uuid.uuid4(), uuid.uuid4()
    db.add_all([Facility(id=fa, name="Test PHC A", level="phc"), Facility(id=fb, name="Test PHC B", level="phc")])
    users = {name: uuid.uuid4() for name in ("asha_a", "doctor_a", "doctor_b", "admin")}
    db.add_all(
        [
            User(id=users["asha_a"], username=f"asha-{users['asha_a'].hex[:6]}", password_hash="x", role="asha", facility_id=fa),
            User(id=users["doctor_a"], username=f"doc-{users['doctor_a'].hex[:6]}", password_hash="x", role="doctor", facility_id=fa),
            User(id=users["doctor_b"], username=f"doc-{users['doctor_b'].hex[:6]}", password_hash="x", role="doctor", facility_id=fb),
            User(id=users["admin"], username=f"admin-{users['admin'].hex[:6]}", password_hash="x", role="admin", facility_id=None),
        ]
    )
    db.flush()
    patient_id = uuid.uuid4()
    db.add(
        Patient(
            id=patient_id,
            abha_number=f"91-{uuid.uuid4().int % 10**12:012d}",
            fhir=build_patient_resource(patient_id=patient_id, abha_number="test", name="Test Child", dob="2024-01-01", gender="female"),
        )
    )
    db.flush()
    encounter_id = new_encounter(db, patient_id, fa, 1)
    db.commit()
    return World(fa, fb, users["asha_a"], users["doctor_a"], users["doctor_b"], users["admin"], patient_id, encounter_id)
