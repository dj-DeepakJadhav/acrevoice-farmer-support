"""Attack on claim #7: state must survive across requests.

``AuditStore`` opens a single ``sqlite3.Connection`` with
``check_same_thread=False`` (``acrevoice/store.py`` line 76) and hands it out to
every request. FastAPI serves each request (and every background task placing
a call) on its own worker thread, so ``AuditStore`` methods are genuinely
called concurrently from multiple threads against that one connection.

Only two methods take ``self._lock`` before touching the connection:
``append`` and ``begin_call``. ``create_case``, ``set_status``, ``get_case``
and ``list_cases`` - the methods the console calls on every single poll and
every status transition - do not. A single shared sqlite3 connection is not
safe to use from multiple threads without external serialisation of *every*
statement, and this reproduces real corruption, not just a logical race.
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from acrevoice.store import AuditStore


def test_concurrent_reads_and_status_changes_do_not_corrupt_the_store():
    """FAILS today: concurrent, unsynchronised access to the shared sqlite3
    connection (used by the console's poll loop and background call threads
    alike) throws sqlite3.InterfaceError / SystemError / TypeError - a crash,
    not merely a stale read. This is exactly the survive-across-requests claim
    the product makes, under the concurrency the real console produces.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store = AuditStore(Path(tmp) / "test.db")
        store.create_case(
            case_id="CASE-RACE", holding_id="H", application_year="2026",
            record={"a": "1"}, status="needs_information", scheme_code="TEST",
        )

        errors: list[BaseException] = []

        def worker(n: int) -> None:
            for i in range(n):
                try:
                    store.set_status(
                        "CASE-RACE",
                        "needs_information" if i % 2 == 0 else "needs_follow_up",
                    )
                    store.get_case("CASE-RACE")
                    store.list_cases()
                except BaseException as exc:  # noqa: BLE001 - we want every crash type
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(150,)) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        store.close()

        assert not errors, (
            f"{len(errors)} exception(s) raised from concurrent AuditStore use "
            f"(e.g. {errors[0]!r}); create_case/set_status/get_case/list_cases "
            "do not hold store._lock, unlike append/begin_call, even though the "
            "connection is shared across threads with check_same_thread=False"
        )


def test_concurrent_calls_on_one_case_are_not_serialised():
    """``begin_call`` exists specifically to 'reserve an attempt before queuing
    work, including across store connections' (its own docstring), but
    ``workflow.run_call`` never calls it - it calls ``store.set_status``
    directly, which is a plain unconditional UPDATE. Two threads racing to
    start a call on the same case both proceed, both append call_started and
    call_ended events, and (with a real CALL-E provider) both would place a
    real, credit-consuming call for the same case.
    """
    import time

    from acrevoice.call_adapter import CallAnswer, CallOutcome
    from acrevoice.workflow import import_case, run_call
    from acrevoice.agent import RecordAgent

    class SlowProvider:
        def collect(self, **kwargs) -> CallOutcome:
            time.sleep(0.15)
            return CallOutcome(
                outcome="completed",
                answers=[CallAnswer(field="cover_crop_used", answer="ja",
                                    confirmed=True, question="Cover crop?", spoken="ja")],
            )

    with tempfile.TemporaryDirectory() as tmp:
        store = AuditStore(Path(tmp) / "test.db")
        case_id = import_case(
            store,
            record={"holding_id": "H", "application_year": "2026", "parcel_id": "P",
                    "cover_crop_used": ""},
            scheme_code="TEST",
            questions={"cover_crop_used": "Cover crop?"},
        )

        outcomes = []

        def worker() -> None:
            try:
                outcomes.append(
                    run_call(store, case_id=case_id, provider=SlowProvider(),
                              farmer_name="Anna", phone="+490",
                              questions={"cover_crop_used": "Cover crop?"},
                              record_agent=RecordAgent())
                )
            except Exception as exc:  # noqa: BLE001 - a rejection is the *expected* outcome
                outcomes.append(exc)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        time.sleep(0.02)
        t2.start()
        t1.join()
        t2.join()

        completed = [o for o in outcomes if isinstance(o, CallOutcome) and o.outcome == "completed"]
        events = store.events(case_id)
        store.close()

        # Expected: a case can only be "in a call" once. The second concurrent
        # attempt should have been rejected, and the log should show exactly
        # one call_started/call_ended pair.
        assert len(completed) <= 1, (
            f"both concurrent call attempts on the same case completed "
            f"({len(completed)} of 2) - nothing serialises run_call against a "
            "case that is already call_in_progress"
        )
        kinds = [e.kind for e in events]
        assert kinds.count("call_started") <= 1, (
            f"expected at most one call_started event for the case, found "
            f"{kinds.count('call_started')} - a real CalleCallProvider would "
            "have placed two live, credit-consuming calls for one case"
        )
