#!/usr/bin/env python3
"""Seed demo patients/encounters/triage records against a running Core service.

Exercises the real API (not direct SQL) so queue reorder, RED escalation,
and audit_log writes all go through actual business logic. Run after
`scripts/seed_facilities_and_users.sql` and after the Core service is up:

    python scripts/seed_demo_patients.py [CORE_SERVICE_URL]

Defaults to http://localhost:8000. Stdlib only, no extra dependencies.
"""
import json
import sys
import urllib.error
import urllib.request

CORE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
PHC_FACILITY_ID = "00000000-0000-0000-0000-000000000002"
RULE_VERSION = "1.0.0"

DEMO_CASES = [
    {
        "abha_number": "12-3456-7890-0001",
        "name": "Aarav Kumar",
        "dob": "2025-11-02",
        "gender": "male",
        "scheme_status": "PMJAY",
        "chief_complaint": "Baby is very drowsy and won't wake up to feed",
        "extracted_facts": {"age_months": 10, "lethargic_or_unconscious": True},
        "severity": "RED",
        "rule_id": "GDS-04",
    },
    {
        "abha_number": "12-3456-7890-0002",
        "name": "Priya Sharma",
        "dob": "2025-06-15",
        "gender": "female",
        "scheme_status": "state",
        "chief_complaint": "Fast, heavy breathing since this morning",
        "extracted_facts": {"age_months": 15, "respiratory_rate_per_min": 45},
        "severity": "YELLOW",
        "rule_id": "RESP-03",
    },
    {
        "abha_number": "12-3456-7890-0003",
        "name": "Rohan Verma",
        "dob": "2023-01-20",
        "gender": "male",
        "scheme_status": "none",
        "chief_complaint": "Mild cough for one day, otherwise playing normally",
        "extracted_facts": {"age_months": 32, "cough_present": True},
        "severity": "GREEN",
        "rule_id": "DEFAULT-01",
    },
    {
        "abha_number": "12-3456-7890-0004",
        "name": "Sita Devi",
        "dob": "2024-09-08",
        "gender": "female",
        "scheme_status": "PMJAY",
        "chief_complaint": "Watery diarrhea for two days, sunken eyes, very thirsty",
        "extracted_facts": {"age_months": 22, "sunken_eyes": True, "skin_pinch_very_slow": True},
        "severity": "RED",
        "rule_id": "DIAR-01",
    },
    {
        "abha_number": "12-3456-7890-0005",
        "name": "Aman Singh",
        "dob": "2022-04-30",
        "gender": "male",
        "scheme_status": "none",
        "chief_complaint": "Fever since yesterday evening",
        "extracted_facts": {"age_months": 46, "fever_present": True},
        "severity": "YELLOW",
        "rule_id": "FEV-03",
    },
]


def call(method, path, body=None, token=None):
    url = f"{CORE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  ! {method} {path} -> {e.code}: {e.read().decode()}", file=sys.stderr)
        raise
    except urllib.error.URLError as e:
        print(f"Cannot reach Core service at {CORE_URL} ({e}). Is it running?", file=sys.stderr)
        sys.exit(1)


def main():
    print(f"Seeding demo patients against {CORE_URL} ...")
    # admin1, not asha1: the demo cases are seeded into the PHC
    # (PHC_FACILITY_ID) so doctor1 -- who is attached to the PHC -- sees them
    # in the queue and dashboard. asha1 is attached to the sub-centre, and
    # require_facility_access() correctly refuses a non-admin token writing
    # into another facility, so seeding as asha1 returned 403 on every
    # /encounters call. admin is the only role permitted to write across
    # facilities, which is what a seeding script is.
    login = call("POST", "/auth/login", {"username": "admin1", "password": "admin-demo-pass"})
    token = login["token"]

    for case in DEMO_CASES:
        print(f"- {case['name']} ({case['abha_number']})")
        call("POST", "/patients", {
            "abha_number": case["abha_number"],
            "name": case["name"],
            "dob": case["dob"],
            "gender": case["gender"],
            "scheme_status": case["scheme_status"],
        }, token)

        encounter = call("POST", "/encounters", {
            "abha_number": case["abha_number"],
            "facility_id": PHC_FACILITY_ID,
            "chief_complaint": case["chief_complaint"],
        }, token)

        call("POST", "/triage", {
            "encounter_id": encounter["id"],
            "complaint_text": case["chief_complaint"],
            "source": "checklist",
            "extracted_facts": case["extracted_facts"],
            "severity": case["severity"],
            "rule_id": case["rule_id"],
            "rule_version": RULE_VERSION,
        }, token)

    print("Done. Log in as doctor1 / doctor-demo-pass to view the queue and dashboard.")


if __name__ == "__main__":
    main()
