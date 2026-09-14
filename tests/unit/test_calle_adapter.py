"""Parsing tests against CALL-E's published response shape.

The fixtures mirror the example in CALL-E's OpenAPI spec (POST /v1/calls, 201).
Getting this right on paper is what stops us burning real calls to discover a
parsing bug.
"""

from __future__ import annotations

import pytest

from acrevoice.call_adapter import CalleCallProvider

RECORD = {"holding_id": "DE-BY-DEMO-001", "application_year": "2026", "parcel_id": "BY-4821-07"}
FIELDS = ["area_ha", "cover_crop_used"]


def call_response(structured=None, *, failure_code=None, attempts=None, status="completed"):
    """Build a response in CALL-E's documented shape."""
    recipient = {
        "id": "rcp_123",
        "phones": ["+4915211966256"],
        "locale": "de-DE",
        "region": "DE",
        "status": status,
        "summary": "Der Landwirt hat beide Angaben bestätigt.",
        "attempts": attempts if attempts is not None else [{
            "id": "att_123",
            "status": status,
            "provider_call_id": "provider_call_123",
            "failure_code": failure_code,
            "failure_message": "n/a" if failure_code else None,
            "transcript_turns": [
                {"offset_seconds": 0, "speaker": "bot", "text": "Wie viele Hektar?"},
                {"offset_seconds": 6, "speaker": "user", "text": "Zweiundvierzig Komma fünf."},
            ],
        }],
    }
    if structured is not None:
        recipient["structured_result"] = structured
    return {
        "id": "call_123",
        "object": "call_task",
        "status": status,
        "recipients": [recipient],
        "summary": "Der Landwirt hat beide Angaben bestätigt.",
        "task_completed": True,
        "completion_confidence": {"score": 0.92, "label": "high"},
        "evidence": ["Der Landwirt sagte 42,5 Hektar."],
        "failure_code": None,
        "failure_message": None,
    }


def parse(call):
    """Exercise the parser without constructing a real client."""
    provider = CalleCallProvider.__new__(CalleCallProvider)
    return provider._to_outcome(call, FIELDS, RECORD, "de")


def test_both_fields_confirmed_completes_the_case():
    out = parse(call_response({
        "consent_given": True,
        "area_ha": "42.5", "area_ha_confirmed": True,
        "cover_crop_used": "ja", "cover_crop_used_confirmed": True,
    }))
    assert out.outcome == "completed"
    assert not out.needs_follow_up
    assert [(a.field, a.answer, a.confirmed) for a in out.answers] == [
        ("area_ha", "42.5", True), ("cover_crop_used", "ja", True)]
    assert out.provider_call_id == "call_123"
    assert out.confidence == 0.92 and out.confidence_label == "high"


def test_transcript_is_captured_for_evidence():
    out = parse(call_response({"consent_given": True, "area_ha": "42.5",
                               "area_ha_confirmed": True, "cover_crop_used": "ja",
                               "cover_crop_used_confirmed": True}))
    assert [t.speaker for t in out.transcript] == ["bot", "user"]
    assert "Zweiundvierzig" in out.transcript[1].text


def test_answer_without_confirmation_is_not_confirmed():
    out = parse(call_response({
        "consent_given": True,
        "area_ha": "42.5", "area_ha_confirmed": False,
        "cover_crop_used": "ja", "cover_crop_used_confirmed": True,
    }))
    assert out.outcome == "partial"
    assert [a.confirmed for a in out.answers] == [False, True]


def test_unknown_value_is_never_confirmed():
    out = parse(call_response({
        "consent_given": True,
        "area_ha": "unknown", "area_ha_confirmed": True,  # provider contradicts itself
        "cover_crop_used": "ja", "cover_crop_used_confirmed": True,
    }))
    assert out.answers[0].confirmed is False


def test_consent_refused_is_refused():
    out = parse(call_response({"consent_given": False}))
    assert out.outcome == "refused"
    assert out.answers == []


@pytest.mark.parametrize("code", ["no_answer", "timed_out", "invalid_phone", "recipient_blocked"])
def test_unreachable_failure_codes(code):
    out = parse(call_response(None, failure_code=code, status="failed"))
    assert out.outcome == "unreachable"
    assert out.failure_code == code
    assert not out.is_account_problem


def test_declined_failure_code_is_refused():
    out = parse(call_response(None, failure_code="declined", status="failed"))
    assert out.outcome == "refused"


@pytest.mark.parametrize("code", ["insufficient_balance", "unsupported_region",
                                  "unsupported_language", "unauthorized"])
def test_account_problems_are_not_blamed_on_the_farmer(code):
    """Out of credits or an unroutable country is our problem, not a follow-up case."""
    out = parse(call_response(None, failure_code=code, status="failed"))
    assert out.outcome == "failed"
    assert out.is_account_problem is True


def test_missing_structured_result_is_unreachable_not_a_crash():
    out = parse(call_response(None))
    assert out.outcome == "unreachable"


def test_empty_recipients_does_not_crash():
    out = parse({"id": "call_1", "status": "failed", "recipients": []})
    assert out.outcome == "unreachable"
