"""Wiring the Strands agent into the call flow.

Every raw answer a provider returns must pass through a record agent's
``normalise`` before an adviser can act on it.  These tests mock the agent -
no real model call ever runs here (see ``conftest.py``).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from acrevoice.call_adapter import DemoCallProvider
from acrevoice.store import AuditStore
from acrevoice.workflow import (
    AWAITING_REVIEW,
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


class StubRecordAgent:
    """A record agent whose replies are fixed per field, for deterministic tests."""

    def __init__(self, replies: dict[str, dict]):
        self.replies = replies
        self.calls: list[tuple[str, str]] = []

    def normalise(self, *, field: str, spoken: str) -> dict:
        self.calls.append((field, spoken))
        return self.replies.get(field, {"value": spoken, "approximate": False, "note": ""})


@pytest.fixture()
def store():
    with tempfile.TemporaryDirectory() as tmp:
        s = AuditStore(Path(tmp) / "test.db")
        yield s
        s.close()


def _call(store, case_id, provider, record_agent=None):
    return run_call(store, case_id=case_id, provider=provider, farmer_name="Anna Bauer",
                    phone="+49000000000", questions=QUESTIONS, record_agent=record_agent)


def test_hedged_answer_normalised_to_unknown_is_never_confirmed(store):
    """A farmer who hedged must not produce a confirmed value, even if the
    provider itself reported the read-back as confirmed."""
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    provider = DemoCallProvider(
        {"area_ha": "42.5", "cover_crop_used": "vielleicht, ich glaube schon"}, confirm=True
    )
    agent = StubRecordAgent({
        "cover_crop_used": {"value": "unknown", "approximate": False, "note": "hedged answer"},
    })

    outcome = _call(store, case_id, provider, record_agent=agent)

    hedged = next(a for a in outcome.answers if a.field == "cover_crop_used")
    assert hedged.confirmed is False
    assert hedged.answer == "unknown"
    assert hedged.spoken == "vielleicht, ich glaube schon"

    confirmed_events = {e.field: e.payload for e in store.events(case_id, kind="answer_captured")}
    assert confirmed_events["cover_crop_used"]["confirmed"] is False
    assert confirmed_events["cover_crop_used"]["note"] == "hedged answer"

    review = review_case(store, case_id=case_id, approved_fields={"area_ha", "cover_crop_used"},
                         reviewer="Adviser")
    assert "cover_crop_used" in review["not_applied_unconfirmed"]
    package = export_correction_package(store, case_id, review)
    assert "cover_crop_used" not in {c["field"] for c in package["changes"]}


def test_approximate_answer_is_flagged(store):
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    provider = DemoCallProvider({"area_ha": "so knapp 43 Hektar ungefähr", "cover_crop_used": "ja"})
    agent = StubRecordAgent({
        "area_ha": {"value": "43", "approximate": True, "note": ""},
    })

    outcome = _call(store, case_id, provider, record_agent=agent)

    area = next(a for a in outcome.answers if a.field == "area_ha")
    assert area.approximate is True
    assert area.answer == "43"

    payload = next(e.payload for e in store.events(case_id, kind="answer_captured")
                  if e.field == "area_ha")
    assert payload["approximate"] is True


def test_raw_spoken_text_survives_verbatim_in_the_evidence_log(store):
    """The spoken text is evidence; normalisation must never overwrite it."""
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    spoken = "zweiundvierzig Komma fünf"
    provider = DemoCallProvider({"area_ha": spoken, "cover_crop_used": "ja"})
    agent = StubRecordAgent({"area_ha": {"value": "42.5", "approximate": False, "note": ""}})

    _call(store, case_id, provider, record_agent=agent)

    payload = next(e.payload for e in store.events(case_id, kind="answer_captured")
                  if e.field == "area_ha")
    assert payload["spoken"] == spoken
    assert payload["answer"] == "42.5"
    assert payload["spoken"] != payload["answer"]


def test_full_flow_with_no_model_provider_available(store, monkeypatch):
    """The demo must still run end to end with no model reachable."""
    monkeypatch.setenv("ACREVOICE_MODEL_PROVIDER", "none")
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    provider = DemoCallProvider({"area_ha": "42.5", "cover_crop_used": "ja"})

    outcome = _call(store, case_id, provider)  # no record_agent injected

    assert outcome.outcome == "completed"
    assert store.get_case(case_id)["status"] == AWAITING_REVIEW
    # The deterministic fallback passes the spoken value through unchanged.
    assert [a.answer for a in outcome.answers] == ["42.5", "ja"]
    assert [a.spoken for a in outcome.answers] == ["42.5", "ja"]

    review = review_case(store, case_id=case_id, approved_fields={"area_ha", "cover_crop_used"},
                         reviewer="Adviser")
    package = export_correction_package(store, case_id, review)
    assert package["record"]["area_ha"] == "42.5"
