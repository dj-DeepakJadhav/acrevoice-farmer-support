"""Attack on claim #5: account failures must not masquerade as farmer failures.

``run_call`` (``acrevoice/workflow.py``) only classifies an outcome as an
account/configuration problem when the *provider returns a CallOutcome* whose
``failure_code`` is in ``call_adapter.ACCOUNT_FAILURES`` (see
``test_calle_adapter.py::test_account_problems_are_not_blamed_on_the_farmer``
and ``test_outcome_recompute.py::test_account_failure_is_unaffected_by_recomputation``,
which both construct the failure this way).

But the real ``calle`` SDK vendored in this project (``calle/errors.py``) does
not always return a structured failure this way: bad credentials or an
exhausted rate limit raise ``CalleAuthenticationError`` / ``CalleRateLimitError``
*before* any ``CallOutcome`` is ever built - see
``calle/generated/errors.py::api_error_from_response``, which maps HTTP 401/403
to ``CalleAuthenticationError`` and 429 to ``CalleRateLimitError``, both raised
as exceptions by ``CalleClient``.

``run_call``'s generic ``except Exception`` handler (workflow.py, "a provider
failure is a case outcome, not a crash") treats *every* provider exception -
regardless of whether it is unmistakably an account/config problem - as a
farmer follow-up: it appends ``call_failed`` and sets the case to
``needs_follow_up``. There is no path from a raised provider exception to
``needs_information`` / a configuration-error classification; that path only
exists for outcomes returned normally with a ``failure_code``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from acrevoice.store import AuditStore
from acrevoice.workflow import NEEDS_FOLLOW_UP, NEEDS_INFORMATION, import_case, run_call

QUESTIONS = {"cover_crop_used": "Cover crop?"}
RECORD = {
    "holding_id": "DE-BY-DEMO-001",
    "application_year": "2026",
    "parcel_id": "BY-4821-07",
    "cover_crop_used": "",
}


def _calle_error(name: str):
    """Build one of the real calle SDK's account-level exceptions."""
    from calle.errors import CalleAPIError

    cls = {
        "auth": __import__("calle.errors", fromlist=["CalleAuthenticationError"]).CalleAuthenticationError,
        "rate_limit": __import__("calle.errors", fromlist=["CalleRateLimitError"]).CalleRateLimitError,
    }[name]
    return cls(code="unauthorized" if name == "auth" else "rate_limit_exceeded",
                message="account problem", status_code=401 if name == "auth" else 429)


@pytest.fixture()
def store():
    with tempfile.TemporaryDirectory() as tmp:
        s = AuditStore(Path(tmp) / "test.db")
        yield s
        s.close()


@pytest.mark.parametrize("failure", ["auth", "rate_limit"])
def test_account_exception_from_the_real_sdk_is_not_a_farmer_follow_up(store, failure):
    """FAILS today: an authentication or rate-limit failure - unambiguously an
    account/config problem, and one the real calle SDK signals by raising,
    not by returning a CallOutcome - still lands the case in
    needs_follow_up, exactly what claim #5 forbids.
    """
    error = _calle_error(failure)

    class RaisingProvider:
        def collect(self, **kwargs):
            raise error

    case_id = import_case(store, record=RECORD, scheme_code="TEST", questions=QUESTIONS)

    with pytest.raises(type(error)):
        run_call(store, case_id=case_id, provider=RaisingProvider(), farmer_name="Anna Bauer",
                 phone="+49000000000", questions=QUESTIONS)

    status = store.get_case(case_id)["status"]
    assert status == NEEDS_INFORMATION, (
        f"case status was {status!r} after a {type(error).__name__}; an account "
        f"or configuration failure must never be filed as {NEEDS_FOLLOW_UP!r} - "
        "that queue is read as 'the farmer needs another call', which is not "
        "true here and cannot be fixed by calling the farmer again"
    )
