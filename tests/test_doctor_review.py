"""Clinician review: separate from the AI result, and additive.

The medical-data-model requirement, as tests: AI prediction, rule-engine evidence,
screening recommendation and clinician review are four separate facts. Recording the
fourth must not change the first three.
"""
from __future__ import annotations

import copy

from tests.conftest import (SCAN_WITH_PII, auth_header, patient_with_shared_scan,
                            signup)

from src.auth import service

DOC = "+919876544001"
SID = SCAN_WITH_PII["scan_id"]


def setup_doctor(client, auth_store):
    """A verified doctor, a scan, and the patient who shared that scan with them.

    The share is not ceremony: reading or reviewing a report requires an active care
    relationship, so a test that skips it is testing a doctor who has no business
    opening this record.
    """
    body = signup(client, DOC, "doctor")
    doctor_id = body["account"]["account_id"]
    service.approve_doctor(doctor_id, approved=True, store=auth_store)
    client.scan_store.save_scan(copy.deepcopy(SCAN_WITH_PII))
    patient_with_shared_scan(client, SCAN_WITH_PII["scan_id"], doctor_id)
    return auth_header(body["token"]), doctor_id


def test_a_doctor_can_record_a_review(client, auth_store, evidence):
    h, _ = setup_doctor(client, auth_store)
    r = client.post(f"/v1/reports/{SID}/review",
                    json={"status": "confirmed", "notes": "agrees with the lesion count"},
                    headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["clinician_review"]["status"] == "confirmed"
    assert body["clinician_review"]["status_label"] == "Confirmed"


def test_all_four_review_statuses_are_accepted(client, auth_store, evidence):
    h, _ = setup_doctor(client, auth_store)
    for status, label in [("reviewed", "Reviewed"),
                          ("needs_further_review", "Needs further review"),
                          ("confirmed", "Confirmed"),
                          ("disagreed", "Disagreed")]:
        r = client.post(f"/v1/reports/{SID}/review", json={"status": status}, headers=h)
        assert r.status_code == 200
        assert r.json()["clinician_review"]["status_label"] == label


def test_an_unknown_status_is_rejected(client, auth_store, evidence):
    h, _ = setup_doctor(client, auth_store)
    r = client.post(f"/v1/reports/{SID}/review", json={"status": "approved"}, headers=h)
    assert r.status_code == 422


def test_the_ai_prediction_is_unchanged_by_a_review(client, auth_store, evidence):
    h, _ = setup_doctor(client, auth_store)
    before = copy.deepcopy(client.scan_store.rows[0])

    client.post(f"/v1/reports/{SID}/review",
                json={"status": "disagreed", "clinician_grade": 4,
                      "notes": "I read this as proliferative"}, headers=h)

    after = client.scan_store.rows[0]
    assert after["icdr_grade"] == before["icdr_grade"] == 2
    assert after["referable"] == before["referable"] is True
    assert after["confidence"] == before["confidence"]
    assert after["rule_grade"] == before["rule_grade"]
    # the scan record gained nothing at all
    assert after == before


def test_the_clinician_result_is_stored_in_a_separate_field(client, auth_store, evidence):
    _, ledger = evidence
    h, _ = setup_doctor(client, auth_store)
    client.post(f"/v1/reports/{SID}/review",
                json={"status": "disagreed", "clinician_grade": 4}, headers=h)

    detail = client.get(f"/v1/reports/{SID}", headers=h).json()
    assert detail["ai"]["icdr_grade"] == 2                 # AI, untouched
    assert detail["clinician_review"]["clinician_grade"] == 4   # clinician, separate
    assert detail["clinician_review"]["status"] == "disagreed"
    # and they are different keys of the document, not the same one
    assert "clinician_grade" not in detail["ai"]
    assert "icdr_grade" not in detail["clinician_review"]


def test_the_review_ledger_is_append_only(client, auth_store, evidence):
    _, ledger = evidence
    h, _ = setup_doctor(client, auth_store)
    client.post(f"/v1/reports/{SID}/review", json={"status": "needs_further_review"}, headers=h)
    client.post(f"/v1/reports/{SID}/review", json={"status": "confirmed"}, headers=h)

    history = ledger.history(SID)
    assert [e["status"] for e in history] == ["needs_further_review", "confirmed"]
    detail = client.get(f"/v1/reports/{SID}", headers=h).json()
    assert detail["clinician_review"]["status"] == "confirmed"       # latest wins
    assert len(detail["clinician_review_history"]) == 2              # history kept


def test_the_review_records_who_made_it(client, auth_store, evidence):
    _, ledger = evidence
    h, account_id = setup_doctor(client, auth_store)
    client.post(f"/v1/reports/{SID}/review", json={"status": "confirmed"}, headers=h)
    assert ledger.latest(SID)["reviewed_by"] == account_id
    assert ledger.latest(SID)["reviewed_at"].endswith("Z")


def test_the_review_status_appears_in_the_report_list(client, auth_store, evidence):
    h, _ = setup_doctor(client, auth_store)
    assert client.get("/v1/reports", headers=h).json()["reports"][0]["review_status"] == "pending"
    client.post(f"/v1/reports/{SID}/review", json={"status": "confirmed"}, headers=h)
    row = client.get("/v1/reports", headers=h).json()["reports"][0]
    assert row["review_status"] == "confirmed"
    assert row["review_status_label"] == "Confirmed"


def test_reviewing_an_unknown_scan_is_a_404(client, auth_store, evidence):
    h, _ = setup_doctor(client, auth_store)
    assert client.post("/v1/reports/sc_nope/review",
                       json={"status": "confirmed"}, headers=h).status_code == 404


def test_the_detail_view_keeps_the_four_layers_separate(client, auth_store, evidence):
    ev, _ = evidence
    h, _ = setup_doctor(client, auth_store)
    ev.save({
        "scan_id": SID,
        "grading": {"icdr_grade": 2, "referable": True, "confidence": 0.91,
                    "per_grade_probability": [0.02, 0.09, 0.61, 0.24, 0.04]},
        "quality": {"gradeable": True, "overall_score": 0.81},
        "rule_check": {"rule_grade": 2, "rule_referable": True,
                       "criteria_fired": ["haemorrhages_present"],
                       "agrees_with_cnn": True, "flag": None,
                       "recommendation": "Refer to ophthalmology"},
        "explain": {"gradcam_available": True, "attention_summary": "on the macula"},
        "lesions": {"microaneurysms": {"count": 14}},
    })
    d = client.get(f"/v1/reports/{SID}", headers=h).json()
    assert d["ai"]["icdr_grade"] == 2
    assert d["rule_engine"]["rule_grade"] == 2
    assert d["rule_engine"]["agrees_with_cnn"] is True
    assert d["screening_recommendation"]["referral"] is True
    assert d["clinician_review"]["status"] == "pending"
    assert d["explain"]["gradcam_available"] is True
    assert d["evidence_available"] is True
