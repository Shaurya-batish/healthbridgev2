import os
import uuid

os.environ.setdefault("JWT_SECRET", "test-secret")

from app.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_round_trip():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_jwt_round_trip_carries_role_and_facility():
    user_id = uuid.uuid4()
    facility_id = uuid.uuid4()

    token = create_access_token(user_id, "doctor", facility_id)
    payload = decode_access_token(token)

    assert payload.user_id == str(user_id)
    assert payload.role == "doctor"
    assert payload.facility_id == str(facility_id)


def test_jwt_allows_null_facility():
    token = create_access_token(uuid.uuid4(), "admin", None)
    payload = decode_access_token(token)
    assert payload.facility_id is None
