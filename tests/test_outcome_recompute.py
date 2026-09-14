"""The call outcome must reflect normalised confirmations, not the provider's
pre-normalisation view.

Regression tests for the T1 defect: a provider can report `confirmed=True` for
a hedged answer, and the agent then normalises it to `unknown`. The case
status must be derived from what ended up confirmed after normalisation, so
`needs_follow_up` stays a queue an adviser can trust (README / ARCHITECTURE).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from acrevoice.call_adapter import DemoCallProvider
from acrevoice.store import AuditStore
from acrevoice.workflow import (
    AWAITING_REVIEW,
    NEEDS_FOLLOW_UP,
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

    def normalise(self, *, field: str, spoken: str) -> dict:
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


def test_provider_confirmed_but_agent_normalises_to_unknown_needs_follow_up(store):
    """Exact reproduction: provider says confirmed, agent says unknown."""
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    provider = DemoCallProvider(
        {"area_ha": "vielleicht, ich glaube schon", "cover_crop_used": "ja"}, confirm=True
    )
    agent = StubRecordAgent({
        "area_ha": {"value": "unknown", "approximate": False, "note": "hedged answer"},
    })

    outcome = _call(store, case_id, provider, record_agent=agent)

    assert outcome.outcome != "completed"
    assert store.get_case(case_id)["status"] == NEEDS_FOLLOW_UP

    from acrevoice.workflow import confirmed_answers
    assert "area_ha" not in confirmed_answers(store, case_id)


def test_approximate_and_hedged_values_are_both_blocked(store):
    """One field normalises cleanly, the other to unknown -> partial -> needs_follow_up,
    while the clean field can still be reviewed and applied."""
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    provider = DemoCallProvider(
        {"area_ha": "so knapp 43 Hektar ungefähr", "cover_crop_used": "vielleicht"}, confirm=True
    )
    agent = StubRecordAgent({
        "area_ha": {"value": "43", "approximate": True, "note": ""},
        "cover_crop_used": {"value": "unknown", "approximate": False, "note": "hedged answer"},
    })

    outcome = _call(store, case_id, provider, record_agent=agent)

    assert outcome.outcome == "partial"
    assert store.get_case(case_id)["status"] == NEEDS_FOLLOW_UP

    review = review_case(store, case_id=case_id, approved_fields={"area_ha", "cover_crop_used"},
                         reviewer="Adviser")
    assert review["applied"] == []
    assert review["not_applied_unconfirmed"] == ["area_ha", "cover_crop_used"]


def test_happy_path_still_reaches_awaiting_review_with_normalisation(store):
    """No regression: clean confirmations through the agent still complete the call."""
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    provider = DemoCallProvider({"area_ha": "42.5", "cover_crop_used": "ja"}, confirm=True)
    agent = StubRecordAgent({})  # passes values through unchanged

    outcome = _call(store, case_id, provider, record_agent=agent)

    assert outcome.outcome == "completed"
    assert store.get_case(case_id)["status"] == AWAITING_REVIEW


def test_consent_refusal_is_unaffected_by_recomputation(store):
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    outcome = _call(store, case_id, DemoCallProvider({"area_ha": "42.5"}, consent=False))

    assert outcome.outcome == "refused"
    assert store.get_case(case_id)["status"] == NEEDS_FOLLOW_UP


def test_account_failure_is_unaffected_by_recomputation(store):
    from acrevoice.call_adapter import CallOutcome
    from acrevoice.workflow import NEEDS_INFORMATION

    class BrokenAccountProvider:
        def collect(self, **kwargs) -> CallOutcome:
            return CallOutcome(outcome="failed", failure_code="insufficient_balance",
                               failure_message="Top up required")

    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    outcome = _call(store, case_id, BrokenAccountProvider())

    assert outcome.outcome == "failed"
    assert outcome.is_account_problem
    assert store.get_case(case_id)["status"] == NEEDS_INFORMATION
