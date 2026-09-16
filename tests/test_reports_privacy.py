"""Report anonymisation.

The fixture scan record deliberately contains a patient name AND a mobile number in its
`patient_ref` field, because that is the realistic failure: the v1 contract says the
field is free text with no PII enforced, so in the field it WILL contain names. These
tests assert that nothing in the doctor-facing API returns it, at any depth of the
response, for the list view or the detail view.
"""
from __future__ import annotations

import json

from tests.conftest import SCAN_WITH_PII, auth_header, signup, patient_with_shared_scan

from src.api.reports import FORBIDDEN_FIELDS
from src.auth import service

DOC = "+919876533001"
PATIENT_NAME = "Lakshmi Narayanan"
PATIENT_MOBILE = "+919812345678"


def verified_doctor(client, auth_store):
    """A verified doctor who has been given access to the PII-laden scan.

    The share matters to these tests specifically. Without it the report list is empty,
    and every "the patient's name does not appear" assertion below would pass for the
    wrong reason — there would be nothing in the response at all. The point is that the
    name is absent from a row that IS returned.
    """
    body = signup(client, DOC, "doctor")
    doctor_id = body["account"]["account_id"]
    service.approve_doctor(doctor_id, approved=True, store=auth_store)
    patient_with_shared_scan(client, SCAN_WITH_PII["scan_id"], doctor_id)
    return auth_header(body["token"])


def _keys(obj, out=None):
    """Every key name anywhere in a nested structure."""
    out = out if out is not None else set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            _keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _keys(v, out)
    return out


def test_report_list_contains_no_patient_name(client, auth_store):
    h = verified_doctor(client, auth_store)
    client.scan_store.save_scan(dict(SCAN_WITH_PII))
    raw = client.get("/v1/reports", headers=h).text
    assert PATIENT_NAME not in raw
    assert "Lakshmi" not in raw


def test_report_list_contains_no_patient_mobile_number(client, auth_store):
    h = verified_doctor(client, auth_store)
    client.scan_store.save_scan(dict(SCAN_WITH_PII))
    raw = client.get("/v1/reports", headers=h).text
    assert PATIENT_MOBILE not in raw
    assert "9812345678" not in raw


def test_report_list_contains_no_identifying_field_names(client, auth_store):
    h = verified_doctor(client, auth_store)
    client.scan_store.save_scan(dict(SCAN_WITH_PII))
    body = client.get("/v1/reports", headers=h).json()
    present = _keys(body)
    for field in FORBIDDEN_FIELDS:
        assert field not in present, f"{field} leaked into the report list"


def test_report_detail_contains_no_patient_identifiers(client, auth_store, evidence):
    ev, _ = evidence
    h = verified_doctor(client, auth_store)
    client.scan_store.save_scan(dict(SCAN_WITH_PII))
    # evidence file also carries the patient_ref, as the analyse response does
    ev.save({"scan_id": SCAN_WITH_PII["scan_id"], "patient_ref": f"{PATIENT_NAME} {PATIENT_MOBILE}",
             "grading": {"icdr_grade": 2, "referable": True, "confidence": 0.91},
             "quality": {"gradeable": True, "overall_score": 0.81},
             "rule_check": {"rule_grade": 2}, "explain": {"gradcam_available": True},
             "lesions": {}})
    raw = client.get(f"/v1/reports/{SCAN_WITH_PII['scan_id']}", headers=h).text
    assert PATIENT_NAME not in raw
    assert PATIENT_MOBILE not in raw
    assert "patient_ref" not in raw


def test_the_scan_record_still_holds_what_it_held(client, auth_store):
    """Anonymisation happens in the serializer, not by deleting data the screening
    workflow owns. The stored record is untouched."""
    h = verified_doctor(client, auth_store)
    client.scan_store.save_scan(dict(SCAN_WITH_PII))
    client.get("/v1/reports", headers=h)
    assert client.scan_store.rows[0]["patient_ref"] == SCAN_WITH_PII["patient_ref"]


def test_reports_are_identified_by_scan_id(client, auth_store):
    h = verified_doctor(client, auth_store)
    client.scan_store.save_scan(dict(SCAN_WITH_PII))
    row = client.get("/v1/reports", headers=h).json()["reports"][0]
    assert row["scan_id"] == SCAN_WITH_PII["scan_id"]
    assert row["ai_grade"] == 2
    assert row["referable"] is True
    assert row["quality_status"] == "pass"
    assert row["review_status"] == "pending"


def test_a_new_pii_field_in_the_scan_record_does_not_leak(client, auth_store):
    """The whitelist property: adding a field to the scan record tomorrow cannot put it
    in the doctor's view without someone editing reports.py on purpose."""
    h = verified_doctor(client, auth_store)
    rec = dict(SCAN_WITH_PII)
    rec["patient_name"] = "Someone Else"
    rec["patient_mobile"] = "+919700000000"
    rec["aadhaar"] = "1234 5678 9012"
    client.scan_store.save_scan(rec)
    raw = client.get("/v1/reports", headers=h).text
    assert "Someone Else" not in raw
    assert "9700000000" not in raw
    assert "1234 5678 9012" not in raw


def test_the_account_store_never_contains_a_retinal_image(client, auth_store):
    signup(client, "+919876533099", "user")
    raw = (auth_store.dir / "accounts.json").read_text()
    for marker in ("png_b64", "gradcam", "image", "scan_id", "icdr"):
        assert marker not in raw


def test_the_admin_doctor_queue_masks_mobile_numbers(client, auth_store, monkeypatch):
    from src.auth import config as cfg
    monkeypatch.setattr(cfg, "ADMIN_MOBILES", ("+919876533050",))
    admin = signup(client, "+919876533050", "user")
    signup(client, DOC, "doctor")
    body = client.get("/v1/auth/admin/doctors",
                      headers=auth_header(admin["token"])).json()
    assert body["doctors"][0]["mobile_masked"].count("*") >= 5
    assert DOC not in json.dumps(body)
