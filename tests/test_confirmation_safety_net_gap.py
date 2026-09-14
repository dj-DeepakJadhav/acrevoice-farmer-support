"""Attack on claim #1: an unconfirmed answer must never reach an approved record.

``run_call`` only downgrades a provider's ``confirmed=True`` to ``confirmed=False``
when the *normalised* value equals ``"unknown"`` (see
``acrevoice/workflow.py::run_call``, the ``confirmed = answer.confirmed and
value.strip().lower() != UNKNOWN`` line). Detecting a hedge such as "vielleicht"
and turning it into ``"unknown"`` is done by the ``normalise_yes_no`` Strands
*tool*, which only runs inside ``StrandsRecordAgent``.

The deterministic fallback agent - ``acrevoice.agent.RecordAgent`` - is used
whenever no model provider is reachable (``build_record_agent()`` falls back to
it, and the test suite's own ``conftest.py`` forces
``ACREVOICE_MODEL_PROVIDER=none`` for exactly this reason). ``RecordAgent.normalise``
does no hedge detection at all - it passes the spoken text through verbatim
(``acrevoice/agent.py`` lines 106-108). So if a call provider (a real bug in
CALL-E's structured extraction, or a provider that just marks anything spoken as
"confirmed") reports ``confirmed=True`` for a hedged answer, and no model is
available, the hedge sails straight through into the approved correction
package - the exact failure this project's docs elsewhere call out as
unacceptable (see ``test_agent_wiring.py::test_hedged_answer_normalised_to_unknown_is_never_confirmed``,
which only exercises the *model-backed* path).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from acrevoice.agent import RecordAgent
from acrevoice.call_adapter import CallAnswer, CallOutcome
from acrevoice.store import AuditStore
from acrevoice.workflow import (
    AWAITING_REVIEW,
    NEEDS_FOLLOW_UP,
    confirmed_answers,
    import_case,
    review_case,
    run_call,
)

QUESTIONS = {"cover_crop_used": "Cover crop?"}
RECORD = {
    "holding_id": "DE-BY-DEMO-001",
    "application_year": "2026",
    "parcel_id": "BY-4821-07",
    "cover_crop_used": "",
}


class HedgeButConfirmedProvider:
    """A provider that reports a plainly hedged spoken answer as confirmed.

    This is exactly the shape of the bug ``test_outcome_recompute.py`` already
    guards against for the model-backed path - the difference here is that no
    model is available, which is the default in this environment (see
    ``conftest.py`` and ``docs`` on the Bedrock free-plan blocker).
    """

    def collect(self, **kwargs) -> CallOutcome:
        return CallOutcome(
            outcome="completed",
            answers=[
                CallAnswer(
                    field="cover_crop_used",
                    answer="vielleicht",
                    confirmed=True,
                    question="Cover crop?",
                    spoken="vielleicht, ich glaube schon",
                )
            ],
        )


@pytest.fixture()
def store():
    with tempfile.TemporaryDirectory() as tmp:
        s = AuditStore(Path(tmp) / "test.db")
        yield s
        s.close()


def test_hedged_answer_survives_as_confirmed_when_no_model_is_available(store):
    """FAILS today: a hedged 'vielleicht' answer, marked confirmed=True by the
    provider, is treated as confirmed because the deterministic RecordAgent
    (the one actually in force whenever no model is reachable) never checks
    for hedge words - only the Strands tool does.
    """
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)

    outcome = run_call(
        store, case_id=case_id, provider=HedgeButConfirmedProvider(),
        farmer_name="Anna Bauer", phone="+49000000000", questions=QUESTIONS,
        record_agent=RecordAgent(),  # the real no-model fallback, not a test stub
    )

    hedged = outcome.answers[0]
    # This is the product's actual claim: a hedge must never end up confirmed.
    assert hedged.confirmed is False, (
        "a hedged spoken answer ('vielleicht, ich glaube schon') was recorded as "
        "confirmed because the deterministic RecordAgent fallback does not "
        "detect hedge words - only the Strands-tool path does"
    )

    case = store.get_case(case_id)
    assert case["status"] == NEEDS_FOLLOW_UP, (
        f"case status was {case['status']!r}; a call whose only answer is an "
        "unconfirmed hedge must never land in awaiting_review"
    )


def test_hedged_answer_must_not_reach_the_approved_record(store):
    """Even if the above is somehow considered 'confirmed', the review step
    must be the last line of defence. It is not: it trusts the (wrongly)
    confirmed flag and writes the hedge phrase straight into the record that
    is meant to go into the official portal.
    """
    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)
    run_call(
        store, case_id=case_id, provider=HedgeButConfirmedProvider(),
        farmer_name="Anna Bauer", phone="+49000000000", questions=QUESTIONS,
        record_agent=RecordAgent(),
    )

    confirmed = confirmed_answers(store, case_id)
    assert "cover_crop_used" not in confirmed

    review = review_case(
        store, case_id=case_id, approved_fields={"cover_crop_used"}, reviewer="Adviser"
    )
    assert "cover_crop_used" not in review["applied"], (
        f"approved_record ended up with cover_crop_used="
        f"{review['approved_record'].get('cover_crop_used')!r} - a hedged, "
        "never-truly-confirmed value reached the record that gets exported "
        "to the official portal"
    )
