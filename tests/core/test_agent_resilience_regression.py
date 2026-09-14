"""Regression coverage for resilient answer normalisation.

A model failure must be recorded per field without discarding a farmer's
already-collected answers. A provider/transport failure remains a failed call.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from acrevoice.call_adapter import CallOutcome, DemoCallProvider
from acrevoice.store import AuditStore
from acrevoice.workflow import (
    CALL_IN_PROGRESS,
    NEEDS_FOLLOW_UP,
    import_case,
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


class RaisingAgent:
    """Stands in for a model timeout / network error during normalisation."""

    def normalise(self, *, field: str, spoken: str) -> dict:
        raise RuntimeError("model timeout")


class NoneReturningAgent:
    def normalise(self, *, field: str, spoken: str) -> dict:
        return None  # type: ignore[return-value]


class NonDictReturningAgent:
    def normalise(self, *, field: str, spoken: str) -> dict:
        return "42.5"  # type: ignore[return-value]


class RaisingProvider:
    """Stands in for a real provider/transport failure - the call never happened."""

    def collect(self, *, farmer_name, phone, record, missing_fields, language, questions=None):
        raise ConnectionError("CALL-E unreachable")


@pytest.fixture()
def store():
    with tempfile.TemporaryDirectory() as tmp:
        s = AuditStore(Path(tmp) / "test.db")
        yield s
        s.close()


def _call(store, case_id, provider, record_agent):
    return run_call(
        store, case_id=case_id, provider=provider, farmer_name="Anna Bauer",
        phone="+49000000000", questions=QUESTIONS, record_agent=record_agent,
    )


def test_agent_exception_does_not_crash_the_call(store):
    """A per-field normalisation failure degrades gracefully: ``run_call``
    returns normally, both answers are still in the audit log, the case
    reaches a terminal status, and the failure is named on the outcome
    rather than raised.
    """
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    provider = DemoCallProvider({"area_ha": "42.5", "cover_crop_used": "ja"})

    outcome = _call(store, case_id, provider, RaisingAgent())

    assert isinstance(outcome, CallOutcome)
    assert "area_ha" in outcome.normalisation_errors
    assert "cover_crop_used" in outcome.normalisation_errors
    assert "model timeout" in outcome.normalisation_errors["area_ha"]

    case = store.get_case(case_id)
    assert case["status"] != CALL_IN_PROGRESS, (
        "case must not be stuck in call_in_progress after an agent failure"
    )
    assert case["status"] in {"awaiting_review", NEEDS_FOLLOW_UP}

    answer_events = store.events(case_id, kind="answer_captured")
    fields = {e.field for e in answer_events}
    assert fields == {"area_ha", "cover_crop_used"}, (
        "the farmer's answers must not be silently dropped when the agent fails"
    )
    for event in answer_events:
        assert event.payload["note"].startswith("normalisation_error:")


def test_agent_returning_none_falls_back_instead_of_crashing(store):
    """BACKLOG T1 item 1/5: malformed agent output ('None') must degrade to the
    raw value, never crash and never silently confirm anything.
    """
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    provider = DemoCallProvider({"area_ha": "42.5", "cover_crop_used": "ja"})

    outcome = _call(store, case_id, provider, NoneReturningAgent())
    assert outcome.outcome in {"partial", "unreachable", "completed"}
    assert set(outcome.normalisation_errors) == {"area_ha", "cover_crop_used"}


def test_agent_returning_non_dict_falls_back_instead_of_crashing(store):
    """Same as above but for a bare string reply instead of a dict."""
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    provider = DemoCallProvider({"area_ha": "42.5", "cover_crop_used": "ja"})

    outcome = _call(store, case_id, provider, NonDictReturningAgent())
    assert outcome.outcome in {"partial", "unreachable", "completed"}
    assert set(outcome.normalisation_errors) == {"area_ha", "cover_crop_used"}


def test_provider_failure_still_raises_and_is_recorded(store):
    """A call that never happened is not the same as a call whose answers we
    could not tidy up: ``provider.collect(...)`` failing must still raise,
    and still leave a ``call_failed`` event with a ``needs_follow_up`` case.
    """
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)

    with pytest.raises(ConnectionError):
        _call(store, case_id, RaisingProvider(), RaisingAgent())

    case = store.get_case(case_id)
    assert case["status"] == NEEDS_FOLLOW_UP

    failed_events = store.events(case_id, kind="call_failed")
    assert failed_events
    assert "CALL-E unreachable" in failed_events[0].payload["error"]


def test_cli_survives_an_agent_that_always_raises(monkeypatch, tmp_path):
    """``python -m acrevoice`` must still print a correction package, not a
    traceback, if normalisation is broken end to end - this is exactly the
    situation ``--live`` must survive without wasting one of ~20 real calls.
    No live call is placed: ``run_demo(live=False)`` uses ``DemoCallProvider``.
    """
    import acrevoice.agent as agent_module

    def _broken_agent(settings=None):
        return RaisingAgent()

    monkeypatch.setattr(agent_module, "build_record_agent", _broken_agent)
    monkeypatch.chdir(tmp_path)

    from acrevoice.__main__ import run_demo

    package = run_demo(live=False)

    assert package["case_id"]
    assert "evidence_timeline" in package
