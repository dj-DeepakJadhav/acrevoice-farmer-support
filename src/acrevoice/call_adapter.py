"""Call providers.

One call collects every missing field for a case, rather than one call per field.
That is better for the farmer and it also matters practically: the hackathon
account has a small fixed number of calls.

CALL-E does the structured extraction itself via ``recipient_result_schema``, so
the adapter's job is to build a faithful task prompt from the locale scripts and
to translate CALL-E's answers back into domain evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Protocol

from .locale import CALL_LOCALE, consent_for, get_script, question_for

# CALL-E's documented convention: "unknown" means not reached or unclear.
UNKNOWN = "unknown"

# CALL-E failure codes, grouped by who needs to act (from the published OpenAPI enums).
REFUSED_FAILURES = {"declined", "policy_violation"}
UNREACHABLE_FAILURES = {
    "no_answer", "timed_out", "invalid_phone", "invalid_recipient",
    "recipient_blocked", "call_failed", "provider_unavailable", "canceled",
}
# These mean the configuration or the account is wrong, not the farmer.
ACCOUNT_FAILURES = {
    "insufficient_balance", "unsupported_region", "unsupported_language",
    "unauthorized", "forbidden", "rate_limit_exceeded", "invalid_request",
    "result_schema_invalid", "recipient_result_schema_invalid",
}


@dataclass(frozen=True)
class CallAnswer:
    field: str
    answer: str
    confirmed: bool
    question: str = ""
    # What the farmer actually said, verbatim - evidence, never overwritten by
    # normalisation.  Defaults to "" only for callers that predate this field.
    spoken: str = ""
    approximate: bool = False


@dataclass
class TranscriptTurn:
    speaker: str
    text: str
    offset_seconds: float = 0.0


@dataclass
class CallOutcome:
    """Everything one phone call produced."""

    outcome: str  # completed | partial | refused | unreachable | failed
    answers: list[CallAnswer] = dc_field(default_factory=list)
    provider_call_id: str = ""
    summary: str = ""
    transcript: list[TranscriptTurn] = dc_field(default_factory=list)
    confidence: float | None = None
    confidence_label: str = ""
    failure_code: str = ""
    failure_message: str = ""
    raw: dict = dc_field(default_factory=dict)
    # Populated when a field's normalisation failed or returned a malformed
    # shape (field name -> error string). Empty means every field that was
    # normalised, normalised cleanly; it says nothing about fields the
    # provider never returned at all.
    normalisation_errors: dict[str, str] = dc_field(default_factory=dict)

    @property
    def needs_follow_up(self) -> bool:
        return self.outcome != "completed"

    @property
    def is_account_problem(self) -> bool:
        """Distinguish our problem from the farmer's - these are not follow-up material."""
        return self.failure_code in ACCOUNT_FAILURES


class CallProvider(Protocol):
    def collect(
        self,
        *,
        farmer_name: str,
        phone: str,
        record: dict[str, str],
        missing_fields: list[str],
        language: str,
        questions: dict[str, str] | None = None,
    ) -> CallOutcome:
        """Place one call and return every answer it produced."""


def build_task(
    *,
    farmer_name: str,
    record: dict[str, str],
    missing_fields: list[str],
    language: str,
    questions: dict[str, str] | None = None,
) -> str:
    """The natural-language brief CALL-E performs on the phone.

    ``questions`` is the scheme's own wording (``schemes.questions_for``) for
    each field; a field missing from it falls back to the generic locale
    phrasing, same as before schemes existed.
    """
    script = get_script(language)
    year = record.get("application_year", "")
    parcel_id = record.get("parcel_id", "")
    supplied = questions or {}
    rendered = [
        supplied.get(f) or question_for(f, language, parcel_id=parcel_id, year=year)
        for f in missing_fields
    ]
    numbered = "\n".join(f"{i}. {q}" for i, q in enumerate(rendered, 1))
    return (
        f"Call {farmer_name} about their {year} agricultural area application.\n\n"
        f"Speak {'German' if language == 'de' else 'English'} for the whole call.\n\n"
        f"Open with consent, using these words:\n{consent_for(language, year=year, count=len(missing_fields))}\n\n"
        f"If they decline or ask to stop, say this and end the call politely:\n{script.refused}\n\n"
        f"If they consent, ask exactly these questions, one at a time:\n{numbered}\n\n"
        f"After each answer, read the value back and ask them to confirm, like this:\n"
        f"{script.read_back.format(value='<their answer>')}\n\n"
        f"Close with:\n{script.closing}\n\n"
        "Do not give advice, do not discuss eligibility, subsidies or payments, and do not "
        "promise any outcome. Only collect and confirm the values above. If a value is not "
        f"clearly given and confirmed, report it as '{UNKNOWN}'."
    )


def build_result_schema(missing_fields: list[str]) -> dict:
    """Ask CALL-E to extract exactly the fields we are missing, plus confirmation."""
    properties: dict[str, dict] = {
        "consent_given": {
            "type": "boolean",
            "description": "True only if the farmer clearly agreed to answer questions.",
        }
    }
    for name in missing_fields:
        properties[name] = {
            "type": "string",
            "description": (
                f"The farmer's stated value for {name.replace('_', ' ')}. "
                f"Use '{UNKNOWN}' if not reached, refused, or unclear."
            ),
        }
        properties[f"{name}_confirmed"] = {
            "type": "boolean",
            "description": f"True only if the farmer confirmed the read-back of {name}.",
        }
    return {"type": "object", "properties": properties, "required": ["consent_given"]}


class DemoCallProvider:
    """Deterministic provider used for development and tests; places no calls."""

    def __init__(self, answers: dict[str, str], *, consent: bool = True, confirm: bool = True):
        self.answers = answers
        self.consent = consent
        self.confirm = confirm

    def collect(self, *, farmer_name, phone, record, missing_fields, language, questions=None) -> CallOutcome:
        task = build_task(
            farmer_name=farmer_name, record=record, missing_fields=missing_fields,
            language=language, questions=questions,
        )
        if not self.consent:
            return CallOutcome(outcome="refused", summary="Farmer declined consent",
                               raw={"task": task})
        supplied = questions or {}
        answers = []
        for name in missing_fields:
            value = self.answers.get(name, UNKNOWN)
            answers.append(
                CallAnswer(
                    field=name,
                    answer=value,
                    confirmed=self.confirm and value != UNKNOWN,
                    question=supplied.get(name) or question_for(
                        name, language, parcel_id=record.get("parcel_id", ""),
                        year=record.get("application_year", "")),
                    spoken=value,
                )
            )
        confirmed = [a for a in answers if a.confirmed]
        outcome = "completed" if len(confirmed) == len(missing_fields) else "partial"
        return CallOutcome(outcome=outcome, answers=answers, provider_call_id="demo",
                           summary="Demo call", raw={"task": task})


class CalleCallProvider:
    """Real outbound calls through CALL-E."""

    def __init__(self, api_key: str, *, timeout: float = 600.0):
        from calle import CalleClient

        self._client = CalleClient(api_key=api_key, timeout=timeout)

    def collect(self, *, farmer_name, phone, record, missing_fields, language, questions=None) -> CallOutcome:
        locale, region = CALL_LOCALE.get(language, CALL_LOCALE["en"])
        task = build_task(
            farmer_name=farmer_name, record=record, missing_fields=missing_fields,
            language=language, questions=questions,
        )
        call = self._client.calls.create_and_wait(
            task=task,
            recipients=[{"phones": [phone], "locale": locale, "region": region}],
            recipient_result_schema=build_result_schema(missing_fields),
            metadata={"holding_id": record.get("holding_id", ""), "language": language},
        )
        return self._to_outcome(call, missing_fields, record, language, questions)

    @staticmethod
    def _recipient(call: dict) -> dict:
        """CALL-E returns one entry per recipient; we always call exactly one."""
        recipients = call.get("recipients") or []
        return recipients[0] if recipients and isinstance(recipients[0], dict) else {}

    @staticmethod
    def _transcript(recipient: dict) -> list[TranscriptTurn]:
        turns: list[TranscriptTurn] = []
        for attempt in recipient.get("attempts") or []:
            for turn in attempt.get("transcript_turns") or []:
                turns.append(
                    TranscriptTurn(
                        speaker=str(turn.get("speaker", "unknown")),
                        text=str(turn.get("text", "")),
                        offset_seconds=float(turn.get("offset_seconds") or 0),
                    )
                )
        return turns

    @staticmethod
    def _failure(call: dict, recipient: dict) -> tuple[str, str]:
        for attempt in reversed(recipient.get("attempts") or []):
            if attempt.get("failure_code"):
                return str(attempt["failure_code"]), str(attempt.get("failure_message") or "")
        if call.get("failure_code"):
            return str(call["failure_code"]), str(call.get("failure_message") or "")
        return "", ""

    def _to_outcome(self, call, missing_fields, record, language, questions=None) -> CallOutcome:
        recipient = self._recipient(call)
        result = recipient.get("structured_result") or call.get("structured_result") or {}
        transcript = self._transcript(recipient)
        failure_code, failure_message = self._failure(call, recipient)
        confidence = call.get("completion_confidence") or {}

        base = {
            "provider_call_id": str(call.get("id") or ""),
            "summary": str(recipient.get("summary") or call.get("summary") or ""),
            "transcript": transcript,
            "confidence": confidence.get("score"),
            "confidence_label": str(confidence.get("label") or ""),
            "failure_code": failure_code,
            "failure_message": failure_message,
            "raw": call,
        }

        # Configuration or account problems are not the farmer's fault.
        if failure_code in ACCOUNT_FAILURES:
            return CallOutcome(outcome="failed", **base)
        if failure_code in REFUSED_FAILURES or result.get("consent_given") is False:
            return CallOutcome(outcome="refused", **base)
        if failure_code in UNREACHABLE_FAILURES or not result:
            return CallOutcome(outcome="unreachable", **base)
        if result.get("consent_given") is not True:
            return CallOutcome(outcome="partial", **base)

        supplied = questions or {}
        answers = []
        for name in missing_fields:
            value = str(result.get(name, UNKNOWN) or UNKNOWN).strip()
            answers.append(
                CallAnswer(
                    field=name,
                    answer=value,
                    confirmed=result.get(f"{name}_confirmed") is True and value.lower() != UNKNOWN,
                    question=supplied.get(name) or question_for(
                        name, language, parcel_id=record.get("parcel_id", ""),
                        year=record.get("application_year", "")),
                    spoken=value,
                )
            )
        confirmed = [a for a in answers if a.confirmed]
        if not confirmed:
            outcome = "unreachable"
        elif len(confirmed) == len(missing_fields):
            outcome = "completed"
        else:
            outcome = "partial"
        return CallOutcome(outcome=outcome, answers=answers, **base)


def build_call_provider(mode: str = "demo", *, answers=None, api_key: str = "") -> CallProvider:
    if mode == "demo":
        return DemoCallProvider(answers or {})
    if mode in ("call-e", "calle"):
        if not api_key:
            raise ValueError("CALLE_API_KEY is required for the call-e provider")
        return CalleCallProvider(api_key)
    raise ValueError(f"Unsupported call provider: {mode}")
