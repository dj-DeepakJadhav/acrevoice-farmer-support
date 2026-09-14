"""Regression coverage for the fix to the defects documented in
test_agent_resilience_regression.py: normalisation of one field must never
affect another field, or the call as a whole.

``run_call`` no longer re-raises a normalisation failure (see
test_agent_resilience_regression.py for why); the field that failed is instead
named in ``CallOutcome.normalisation_errors``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from acrevoice.call_adapter import DemoCallProvider
from acrevoice.store import AuditStore
from acrevoice.workflow import CALL_IN_PROGRESS, import_case, run_call

QUESTIONS = {"area_ha": "How many hectares?", "cover_crop_used": "Cover crop?"}
RECORD = {
    "holding_id": "DE-BY-DEMO-001",
    "application_year": "2026",
    "parcel_id": "BY-4821-07",
    "area_ha": "",
    "cover_crop_used": "",
}


class PartiallyRaisingAgent:
    """Fails on exactly one field; the other must still be normalised."""

    def normalise(self, *, field: str, spoken: str) -> dict:
        if field == "area_ha":
            raise RuntimeError("model timeout")
        return {"value": "yes", "approximate": False, "note": ""}


@pytest.fixture()
def store():
    with tempfile.TemporaryDirectory() as tmp:
        s = AuditStore(Path(tmp) / "test.db")
        yield s
        s.close()


def test_one_field_normalisation_failure_does_not_affect_the_other(store):
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    provider = DemoCallProvider({"area_ha": "42.5", "cover_crop_used": "ja"})

    outcome = run_call(
        store, case_id=case_id, provider=provider, farmer_name="Anna Bauer",
        phone="+49000000000", questions=QUESTIONS, record_agent=PartiallyRaisingAgent(),
    )
    assert set(outcome.normalisation_errors) == {"area_ha"}
    assert "model timeout" in outcome.normalisation_errors["area_ha"]

    case = store.get_case(case_id)
    assert case["status"] != CALL_IN_PROGRESS

    events = {e.field: e for e in store.events(case_id, kind="answer_captured")}
    assert set(events) == {"area_ha", "cover_crop_used"}

    # The field whose normalisation raised keeps the provider's raw answer and
    # confirmation, and the audit trail notes that normalisation didn't run.
    failed = events["area_ha"]
    assert failed.payload["answer"] == "42.5"
    assert failed.payload["confirmed"] is True
    assert "normalisation_error" in failed.payload.get("note", "")

    # The field whose normalisation succeeded is unaffected by the other's failure.
    ok = events["cover_crop_used"]
    assert ok.payload["answer"] == "yes"
    assert ok.payload["confirmed"] is True
