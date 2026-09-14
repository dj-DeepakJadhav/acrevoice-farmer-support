"""End-to-end case workflow, backed by the append-only audit store.

State model (docs/APP_DESIGN.md):

    imported -> needs_information -> call_in_progress -> awaiting_review -> closed
                                                      -> needs_follow_up

A call that is refused, unreachable or only partly answered never lands in
``awaiting_review``; it becomes ``needs_follow_up`` so an adviser cannot mistake
an unconfirmed value for a confirmed one.
"""

from __future__ import annotations

import uuid
from dataclasses import replace

from calle.errors import CalleAuthenticationError, CalleRateLimitError

from . import agent as agent_module
from .agent import RecordAgent
from .call_adapter import UNKNOWN, CallOutcome, CallProvider
from .store import AuditStore

NEEDS_INFORMATION = "needs_information"
CALL_IN_PROGRESS = "call_in_progress"
AWAITING_REVIEW = "awaiting_review"
NEEDS_FOLLOW_UP = "needs_follow_up"
CLOSED = "closed"


def find_missing(record: dict[str, str], questions: dict[str, str]) -> list[str]:
    """A field is missing when the record has no non-empty value for it."""
    return [name for name in questions if not (record.get(name) or "").strip()]


def import_case(
    store: AuditStore,
    *,
    record: dict[str, str],
    scheme_code: str,
    questions: dict[str, str],
    language: str = "de",
) -> str:
    """A case always belongs to exactly one CAP scheme (see ``schemes.py``);
    that is what tells an adviser and the console which questions, labels and
    why-it-matters text apply.
    """
    missing = find_missing(record, questions)
    case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"
    store.create_case(
        case_id=case_id,
        holding_id=record.get("holding_id", ""),
        holding_name=record.get("holding_name", ""),
        application_year=record.get("application_year", ""),
        record=record,
        status=NEEDS_INFORMATION if missing else CLOSED,
        scheme_code=scheme_code,
        language=language,
    )
    store.append(case_id, "missing_fields_identified", payload={"fields": missing})
    return case_id


def run_call(
    store: AuditStore,
    *,
    case_id: str,
    provider: CallProvider,
    farmer_name: str,
    phone: str,
    questions: dict[str, str],
    record_agent: RecordAgent | None = None,
    reserved: bool = False,
) -> CallOutcome:
    case = store.get_case(case_id)
    if case is None:
        raise KeyError(f"Unknown case {case_id}")

    record = case["original_record"]
    language = case["language"]
    missing = find_missing(record, questions)

    if not missing:
        raise ValueError("No missing fields to call about")
    if not reserved:
        store.begin_call(case_id, payload={"farmer": farmer_name, "language": language, "fields": missing})
    elif case["status"] != CALL_IN_PROGRESS:
        raise ValueError("Call reservation is no longer active")

    try:
        outcome = provider.collect(
            farmer_name=farmer_name, phone=phone, record=record,
            missing_fields=missing, language=language, questions=questions,
        )
    except (CalleAuthenticationError, CalleRateLimitError) as exc:
        # The calle SDK signals bad credentials and exhausted rate limits by
        # raising, not by returning a CallOutcome with a failure_code - but
        # they are still ours to fix, never the farmer's, so they must not
        # fall into the generic handler below and become a follow-up case.
        store.append(case_id, "call_configuration_error",
                     payload={"failure_code": getattr(exc, "code", "") or type(exc).__name__,
                              "failure_message": str(exc)})
        store.set_status(case_id, NEEDS_INFORMATION)
        raise
    except Exception as exc:  # noqa: BLE001 - a provider failure is a case outcome, not a crash
        store.append(case_id, "call_failed", payload={"error": f"{type(exc).__name__}: {exc}"})
        store.set_status(case_id, NEEDS_FOLLOW_UP)
        raise

    if outcome.outcome == "refused" or outcome.is_account_problem:
        outcome.answers = []
    notes: dict[str, str] = {}
    normalisation_errors: dict[str, str] = {}
    if outcome.answers:
        # Built once per call, not once per field - each normalise() is a network call.
        # Looked up via the module (not imported by name) so callers - notably the
        # CLI and tests - can monkeypatch acrevoice.agent.build_record_agent.
        try:
            agent = record_agent or agent_module.build_record_agent()
        except Exception:
            agent = agent_module.RecordAgent()
        normalised = []
        for answer in outcome.answers:
            if answer.field not in missing:
                continue
            raw = answer.spoken or answer.answer
            # Normalisation is an enhancement, never a precondition for recording an
            # answer: a per-field model failure or malformed reply must fall back to
            # the provider's raw, already-collected answer rather than lose it.
            value, approximate = raw, answer.approximate
            try:
                result = agent.normalise(field=answer.field, spoken=raw)
            except Exception as exc:  # noqa: BLE001 - a model timeout is not a farmer failure
                error = f"{type(exc).__name__}: {exc}"
                normalisation_errors[answer.field] = error
                notes[answer.field] = f"normalisation_error: {error}"
            else:
                if isinstance(result, dict) and isinstance(result.get("value"), str) and result["value"].strip():
                    value = result["value"].strip()
                    approximate = approximate or result.get("approximate", False) is not False
                    note = str(result.get("note") or "").strip()
                    if note:
                        notes[answer.field] = note
                else:
                    error = "malformed agent reply, kept raw answer"
                    normalisation_errors[answer.field] = error
                    notes[answer.field] = f"normalisation_error: {error}"
            # A hedged answer must never end up confirmed, whatever the provider claimed.
            # On normalisation failure the provider's own confirmed answer is kept verbatim.
            safety = agent_module.RecordAgent().normalise(field=answer.field, spoken=raw)
            approximate = approximate or safety.get("approximate", False)
            if safety.get("note") == "hedged answer":
                value = UNKNOWN
            confirmed = answer.confirmed is True and value.strip().lower() != UNKNOWN and not approximate
            normalised.append(replace(answer, answer=value, approximate=approximate, confirmed=confirmed))
        outcome.answers = normalised
        outcome.normalisation_errors = normalisation_errors

        # The provider computed `outcome` from its own, pre-normalisation view of
        # the answers. The agent can downgrade a confirmed-but-hedged answer to
        # unknown, so the outcome - and the case status derived from it - must be
        # recomputed from what actually ended up confirmed, not from the
        # provider's stale count.
        confirmed_count = len({a.field for a in outcome.answers if a.confirmed})
        if not confirmed_count:
            outcome.outcome = "partial"
        elif confirmed_count == len(missing):
            outcome.outcome = "completed"
        else:
            outcome.outcome = "partial"

    for answer in outcome.answers:
        payload = {"question": answer.question, "spoken": answer.spoken,
                   "answer": answer.answer, "approximate": answer.approximate,
                   "confirmed": answer.confirmed}
        if answer.field in notes:
            payload["note"] = notes[answer.field]
        store.append(case_id, "answer_captured", field=answer.field, payload=payload)

    if outcome.transcript:
        store.append(case_id, "transcript_recorded",
                     payload={"turns": [{"speaker": t.speaker, "text": t.text,
                                         "at_seconds": t.offset_seconds}
                                        for t in outcome.transcript]})

    store.append(case_id, "call_ended",
                 payload={"outcome": outcome.outcome,
                          "provider_call_id": outcome.provider_call_id,
                          "summary": outcome.summary,
                          "confidence": outcome.confidence,
                          "confidence_label": outcome.confidence_label,
                          "failure_code": outcome.failure_code,
                          "failure_message": outcome.failure_message})

    # An account or configuration failure is ours to fix, not a farmer follow-up.
    if outcome.is_account_problem:
        store.append(case_id, "call_configuration_error",
                     payload={"failure_code": outcome.failure_code,
                              "failure_message": outcome.failure_message})
        store.set_status(case_id, NEEDS_INFORMATION)
        return outcome

    store.set_status(case_id, AWAITING_REVIEW if outcome.outcome == "completed" else NEEDS_FOLLOW_UP)

    # A normalisation failure is not a failed call: the farmer answered, the
    # answers were captured and confirmed, and the case is approvable as-is.
    # The audit trail and case status are already durable at this point, so
    # there is nothing left to protect by raising - it would only turn a
    # degraded-but-successful call into a crash for every caller, including
    # the CLI that places the one real, credit-costing call. Failures are
    # reported on the outcome instead, per field.
    return outcome


def confirmed_answers(store: AuditStore, case_id: str) -> dict[str, dict]:
    """Latest confirmed answer per field, read back from the audit log."""
    out: dict[str, dict] = {}
    for event in store.events(case_id, kind="answer_captured"):
        out.pop(event.field, None)
        if (event.payload.get("confirmed") is True and not event.payload.get("approximate")
                and str(event.payload.get("answer", "")).strip().lower() not in ("", UNKNOWN)):
            out[event.field] = {**event.payload, "captured_at": event.created_at,
                               "evidence_id": event.event_id}
    return out


def review_case(
    store: AuditStore, *, case_id: str, approved_fields: set[str], reviewer: str, notes: str = ""
) -> dict:
    """Apply only approved AND confirmed answers. The source record is never overwritten."""
    case = store.get_case(case_id)
    if case is None:
        raise KeyError(f"Unknown case {case_id}")

    if case["status"] in (CALL_IN_PROGRESS, CLOSED):
        raise ValueError("Case cannot be reviewed while calling or after closure")

    original = case["original_record"]
    confirmed = confirmed_answers(store, case_id)
    approved_record = dict(original)
    applied, rejected = [], []

    for name in sorted(approved_fields):
        if name in confirmed:
            approved_record[name] = confirmed[name]["answer"]
            applied.append(name)
        else:
            rejected.append(name)

    result = {"approved_record": approved_record, "applied": applied,
              "not_applied_unconfirmed": rejected,
              "review": {"reviewer": reviewer, "notes": notes}}
    store.append(case_id, "reviewed",
                 payload={"reviewer": reviewer, "notes": notes, "applied": applied,
                          "not_applied_unconfirmed": rejected, "result": result})
    store.set_status(case_id, CLOSED)
    return result


def export_correction_package(store: AuditStore, case_id: str, review: dict | None = None) -> dict:
    """A portable package for a human to enter into the official portal."""
    case = store.get_case(case_id)
    if case is None:
        raise KeyError(case_id)
    if review is None:
        reviews = store.events(case_id, kind="reviewed")
        if not reviews or "result" not in reviews[-1].payload:
            raise ValueError("No saved adviser-approved correction package")
        review = reviews[-1].payload["result"]
    original = case["original_record"]
    approved = review["approved_record"]
    confirmed = confirmed_answers(store, case_id)

    changes = [
        {
            "field": name,
            "original": original.get(name, ""),
            "proposed": approved.get(name, ""),
            "confirmed": True,
            "question": confirmed[name]["question"],
            "captured_at": confirmed[name]["captured_at"],
        }
        for name in review["applied"]
        if original.get(name, "") != approved.get(name, "")
    ]
    return {
        "case_id": case_id,
        "holding_id": case["holding_id"],
        "application_year": case["application_year"],
        "language": case["language"],
        "status": case["status"],
        "record": approved,
        "original_record": original,
        "changes": changes,
        "not_applied_unconfirmed": review["not_applied_unconfirmed"],
        "review": review["review"],
        "evidence_timeline": store.timeline(case_id),
    }
