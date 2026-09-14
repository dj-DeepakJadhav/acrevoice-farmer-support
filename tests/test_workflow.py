"""Workflow tests, with emphasis on the paths where a wrong answer does harm."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from acrevoice.call_adapter import DemoCallProvider
from acrevoice.store import AuditStore
from acrevoice.workflow import (
    AWAITING_REVIEW,
    CLOSED,
    NEEDS_FOLLOW_UP,
    NEEDS_INFORMATION,
    export_correction_package,
    import_case,
    review_case,
    run_call,
)

QUESTIONS = {"area_ha": "How many hectares?", "cover_crop_used": "Cover crop?"}
RECORD = {
    "holding_id": "DE-BY-DEMO-001",
    "application_year": "2026",
    "parcel_id": "BY-4821-07",
    "area_ha": "",
    "cover_crop_used": "",
}


@pytest.fixture()
def store():
    with tempfile.TemporaryDirectory() as tmp:
        s = AuditStore(Path(tmp) / "test.db")
        yield s
        s.close()


def _call(store, case_id, provider):
    return run_call(store, case_id=case_id, provider=provider, farmer_name="Anna Bauer",
                    phone="+49000000000", questions=QUESTIONS)


def test_import_case_requires_a_scheme_code(store):
    """A case with no scheme has no question wording, no labels, no why - it
    cannot be shown to an adviser at all."""
    with pytest.raises(TypeError):
        import_case(store, record=RECORD, questions=QUESTIONS)  # type: ignore[call-arg]


def test_happy_path_exports_both_confirmed_fields(store):
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS, language="de")
    assert store.get_case(case_id)["status"] == NEEDS_INFORMATION

    outcome = _call(store, case_id, DemoCallProvider({"area_ha": "42.5", "cover_crop_used": "ja"}))
    assert outcome.outcome == "completed"
    assert store.get_case(case_id)["status"] == AWAITING_REVIEW

    review = review_case(store, case_id=case_id, approved_fields={"area_ha", "cover_crop_used"},
                         reviewer="Adviser")
    package = export_correction_package(store, case_id, review)
    assert package["record"]["area_ha"] == "42.5"
    assert {c["field"] for c in package["changes"]} == {"area_ha", "cover_crop_used"}
    assert all(c["original"] == "" for c in package["changes"])
    assert store.get_case(case_id)["status"] == CLOSED


def test_refused_consent_becomes_follow_up_and_exports_nothing(store):
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    outcome = _call(store, case_id, DemoCallProvider({"area_ha": "42.5"}, consent=False))

    assert outcome.outcome == "refused"
    assert outcome.needs_follow_up
    assert store.get_case(case_id)["status"] == NEEDS_FOLLOW_UP

    review = review_case(store, case_id=case_id, approved_fields={"area_ha"}, reviewer="Adviser")
    package = export_correction_package(store, case_id, review)
    assert package["changes"] == []
    assert package["record"] == RECORD


def test_unreachable_farmer_never_produces_a_confirmed_value(store):
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    outcome = _call(store, case_id, DemoCallProvider({}))  # every answer -> unknown

    assert all(not a.confirmed for a in outcome.answers)
    assert store.get_case(case_id)["status"] == NEEDS_FOLLOW_UP

    review = review_case(store, case_id=case_id, approved_fields={"area_ha"}, reviewer="Adviser")
    assert review["not_applied_unconfirmed"] == ["area_ha"]
    assert export_correction_package(store, case_id, review)["changes"] == []


def test_partial_answers_do_not_reach_awaiting_review(store):
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    outcome = _call(store, case_id, DemoCallProvider({"area_ha": "42.5"}))  # second field unknown

    assert outcome.outcome == "partial"
    assert store.get_case(case_id)["status"] == NEEDS_FOLLOW_UP

    review = review_case(store, case_id=case_id, approved_fields={"area_ha", "cover_crop_used"},
                         reviewer="Adviser")
    assert review["applied"] == ["area_ha"]
    assert review["not_applied_unconfirmed"] == ["cover_crop_used"]


def test_answer_given_but_read_back_not_confirmed_is_not_applied(store):
    """The read-back is the safety feature: answered is not the same as confirmed."""
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    provider = DemoCallProvider({"area_ha": "42.5", "cover_crop_used": "ja"}, confirm=False)
    outcome = _call(store, case_id, provider)

    assert [a.answer for a in outcome.answers] == ["42.5", "ja"]
    assert all(not a.confirmed for a in outcome.answers)

    review = review_case(store, case_id=case_id, approved_fields={"area_ha"}, reviewer="Adviser")
    assert review["applied"] == []
    assert export_correction_package(store, case_id, review)["changes"] == []


def test_adviser_can_approve_a_subset(store):
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    _call(store, case_id, DemoCallProvider({"area_ha": "42.5", "cover_crop_used": "ja"}))

    review = review_case(store, case_id=case_id, approved_fields={"area_ha"}, reviewer="Adviser")
    package = export_correction_package(store, case_id, review)
    assert [c["field"] for c in package["changes"]] == ["area_ha"]
    assert package["record"]["cover_crop_used"] == ""


def test_export_carries_evidence_with_question_and_timestamp(store):
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    _call(store, case_id, DemoCallProvider({"area_ha": "42.5", "cover_crop_used": "ja"}))
    review = review_case(store, case_id=case_id, approved_fields={"area_ha"}, reviewer="Adviser")
    change = export_correction_package(store, case_id, review)["changes"][0]

    assert change["question"]
    assert change["captured_at"].endswith("+00:00")
    assert change["confirmed"] is True


def test_audit_log_is_append_only(store):
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    _call(store, case_id, DemoCallProvider({"area_ha": "42.5"}))

    with pytest.raises(Exception, match="append-only"):
        store._conn.execute("UPDATE events SET payload='{}' WHERE case_id=?", (case_id,))
    with pytest.raises(Exception, match="append-only"):
        store._conn.execute("DELETE FROM events WHERE case_id=?", (case_id,))
