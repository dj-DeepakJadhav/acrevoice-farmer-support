"""Adviser console API.

Two deliberate differences from the first prototype:

* Case state lives in SQLite, so it survives requests and restarts.
* ``/api/review`` reviews what the log already contains.  It never places a call
  of its own - an endpoint that manufactures the evidence it then approves would
  make the audit trail worthless.

A real call takes minutes, so calls run as a background task and the UI polls.

Every case belongs to a CAP scheme (``schemes.py``); the console reads the
scheme's own question wording, field labels and why-it-matters text in the
case's call language, never the console language - the farmer's script and
the adviser's chrome are independent (``locale.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import io, schemes, sources
from .call_adapter import build_call_provider
from .agent import RecordAgent
from .locale import SUPPORTED, ui_strings
from .config import Settings
from .sample_case import ANSWERS_BY_FIELD, seed_queue
from .store import AuditStore
from .workflow import (
    AWAITING_REVIEW,
    CALL_IN_PROGRESS,
    CLOSED,
    NEEDS_FOLLOW_UP,
    NEEDS_INFORMATION,
    confirmed_answers,
    export_correction_package,
    find_missing,
    import_case,
    review_case,
    run_call,
)

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="AcreVoice adviser console")
app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")
store = AuditStore("acrevoice.db")
settings = Settings.from_env()

# The order an adviser should work a queue in: a case that already needs a
# follow-up is the most urgent, a closed case the least.
STATUS_ORDER = {
    NEEDS_FOLLOW_UP: 0,
    NEEDS_INFORMATION: 1,
    CALL_IN_PROGRESS: 2,
    AWAITING_REVIEW: 3,
    CLOSED: 4,
}


class ReviewRequest(BaseModel):
    approved_fields: list[str]
    reviewer: str = "Demo adviser"
    notes: str = ""


class CallRequest(BaseModel):
    live: bool = False
    farmer_name: str = "Anna Bauer"
    scenario: Literal["confirmed", "uncertain", "refused", "unreachable", "configuration"] = "confirmed"


class LanguageRequest(BaseModel):
    language: str


class SupportRequest(BaseModel):
    holding_name: str = "Demo Farm — not a real applicant"
    farmer_name: str = "Anna Bauer"
    land: Literal["Bayern"] = "Bayern"
    topic: Literal["eco_scheme", "multiple_application"] = "eco_scheme"
    language: Literal["de", "en"] = "de"
    callback_requested: bool = True


class ExpertRouteRequest(BaseModel):
    reason: str = "Needs adviser verification"
    question: str = "Please verify the request against the official source and holding facts."
    assignee: str = "Farm advisory desk"


def _scheme_view(case: dict) -> dict:
    scheme = schemes.get_scheme(case["scheme_code"])
    language = case["language"]
    return {
        "code": scheme.code,
        "name": scheme.name[language],
        "programme": scheme.programme[language],
        "summary": scheme.summary[language],
        "payment": scheme.payment[language],
        "source": scheme.source,
    }


def _last_activity(case_id: str) -> str:
    events = store.events(case_id)
    return events[-1].created_at if events else ""


def case_summary(case: dict) -> dict:
    """The queue-row view: enough to list and sort a case, nothing evidentiary."""
    case_id = case["case_id"]
    language = case["language"]
    questions = schemes.questions_for(case["scheme_code"], language)
    missing = find_missing(case["original_record"], questions)
    confirmed = confirmed_answers(store, case_id)
    return {
        "case_id": case_id,
        "holding_id": case["holding_id"],
        "holding_name": case["holding_name"],
        "application_year": case["application_year"],
        "status": case["status"],
        "language": language,
        "scheme": _scheme_view(case),
        "missing_count": len(missing),
        "confirmed_count": len(confirmed),
        "last_activity": _last_activity(case_id),
    }


def case_detail(case_id: str) -> dict:
    case = store.get_case(case_id)
    if case is None:
        raise HTTPException(404, ui_strings(settings.language)["error_case_not_found"])
    language = case["language"]
    scheme = schemes.get_scheme(case["scheme_code"])
    questions = schemes.questions_for(case["scheme_code"], language)
    labels = schemes.labels_for(case["scheme_code"], language)
    confirmed = confirmed_answers(store, case_id)

    answers = []
    for e in store.events(case_id, kind="answer_captured"):
        scheme_field = scheme.field(e.field)
        answers.append({
            "field": e.field,
            "label": labels.get(e.field, e.field.replace("_", " ")),
            "question": e.payload.get("question", ""),
            "why": scheme_field.why[language] if scheme_field else "",
            "spoken": e.payload.get("spoken", ""),
            "answer": e.payload.get("answer", ""),
            "confirmed": e.payload.get("confirmed", False),
            "approximate": e.payload.get("approximate", False),
            "note": e.payload.get("note", ""),
            "captured_at": e.created_at,
        })

    fields = [
        {
            "name": f.name,
            "label": f.label[language],
            "why": f.why[language],
            "kind": f.kind,
            "original_value": case["original_record"].get(f.name, ""),
        }
        for f in scheme.fields
    ]

    history = []
    for event in store.events(case_id):
        if event.kind == "call_started":
            history.append({"started_at": event.created_at, "outcome": "running",
                            "provider": event.payload.get("provider", "unknown"), "transcript": []})
        elif history and event.kind == "transcript_recorded":
            history[-1]["transcript"] = event.payload.get("turns", [])
        elif history and event.kind in ("call_ended", "call_failed", "call_configuration_error"):
            history[-1].update({"ended_at": event.created_at,
                               "outcome": "configuration" if event.kind == "call_configuration_error" else
                                          "failed" if event.kind == "call_failed" else event.payload.get("outcome"),
                               "provider_call_id": event.payload.get("provider_call_id", "")})
    last = history[-1]["outcome"] if history else ""
    next_action = ("closed" if case["status"] == CLOSED else "wait" if case["status"] == CALL_IN_PROGRESS else
                   "configuration" if last == "configuration" else "failed" if last == "failed" else
                   "refused" if last == "refused" else "unreachable" if last == "unreachable" else
                   "review" if case["status"] == AWAITING_REVIEW else "follow_up" if history else "call")
    package = None
    if store.events(case_id, kind="reviewed"):
        try:
            package = export_correction_package(store, case_id)
        except ValueError:
            pass
    return {
        **case_summary(case),
        "missing_fields": find_missing(case["original_record"], questions),
        "confirmed_fields": sorted(confirmed),
        "answers": answers,
        "fields": fields,
        "timeline": store.timeline(case_id),
        "call_history": history,
        "next_action": next_action,
        "correction_package": package,
        "support_goal": ({
            "topic": case["support_topic"], "goal_step": case["goal_step"],
            "source_cards": case["source_cards"], "expert_route": case["expert_route"],
            "eligibility_disclaimer": (
                "AcreVoice gibt keine Förderzusage. Quellen und Angaben werden von Menschen geprüft."
                if language == "de" else
                "AcreVoice does not decide eligibility. Sources and facts are checked by people."
            ),
        } if case["case_kind"] == "support" else None),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/cases")
def list_cases() -> list[dict]:
    cases = store.list_cases()
    if not cases:
        seed_queue(store)
        cases = store.list_cases()
    cases.sort(key=lambda c: STATUS_ORDER.get(c["status"], len(STATUS_ORDER)))
    return [case_summary(c) for c in cases]


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict:
    return case_detail(case_id)


@app.get("/api/funding-sources")
def funding_sources(land: str = "Bayern", topic: str = "eco_scheme", language: str = "de") -> dict:
    if language not in SUPPORTED:
        raise HTTPException(400, f"Unsupported language {language!r}")
    cards = sources.match_sources(land=land, topic=topic, language=language)
    if not cards:
        raise HTTPException(404, "No reviewed source is available for that Bavaria-first request")
    return {"land": land, "topic": topic, "sources": cards,
            "disclaimer": "Keine Förderzusage; menschliche Prüfung erforderlich."
            if language == "de" else "No eligibility decision; human verification required."}


@app.post("/api/support-goals")
def create_support_goal(body: SupportRequest) -> dict:
    cards = sources.match_sources(land=body.land, topic=body.topic, language=body.language)
    if not cards:
        raise HTTPException(400, "No reviewed source is available for this request")
    import uuid
    case_id = f"GOAL-{uuid.uuid4().hex[:8].upper()}"
    # Reuse the established evidence fields for the initial ÖR2 vertical slice.
    # They remain blank until the farmer consents to a callback and answers.
    record = {"holding_id": "", "holding_name": body.holding_name, "application_year": "2026",
              "hauptfruchtarten": "", "leguminosen_anteil": ""}
    store.create_support_case(case_id=case_id, holding_name=body.holding_name,
                              language=body.language, topic=body.topic,
                              source_cards=cards, record=record)
    if body.callback_requested:
        store.set_goal_step(case_id, "awaiting_callback")
    else:
        store.route_to_expert(case_id, reason="Callback not requested",
                              question="Please provide source guidance without collecting phone evidence.")
    return case_detail(case_id)


@app.get("/api/support-goals")
def list_support_goals() -> list[dict]:
    return [case_detail(case["case_id"]) for case in store.list_cases() if case["case_kind"] == "support"]


@app.get("/api/support-goals/{case_id}")
def get_support_goal(case_id: str) -> dict:
    detail = case_detail(case_id)
    if detail["support_goal"] is None:
        raise HTTPException(404, "Support goal not found")
    return detail


@app.post("/api/import/csv", response_model=None)
def import_csv(file: UploadFile) -> dict | JSONResponse:
    """Bulk-import a FALK-style CSV: one row becomes one case, one blank cell
    becomes one missing field to call about. Validated up front so a bad
    scheme code in row five does not leave rows one through four imported.

    Errors come back as ``{"error": "<German message>"}`` with a 400 status,
    never a bare 500 or an empty body - an adviser has to know which row to fix.
    """
    strings = ui_strings(settings.language)
    try:
        cases = io.record_from_csv(file.file)
    except Exception as exc:  # noqa: BLE001 - a malformed upload is a 400, not a crash
        message = strings["error_upload_failed"].format(message=str(exc))
        return JSONResponse(status_code=400, content={"error": message})
    try:
        prepared = [
            (case_data, schemes.questions_for(case_data["scheme_code"], settings.language))
            for case_data in cases
        ]
    except ValueError as exc:
        row = next((i for i, c in enumerate(cases, start=1)
                    if c["scheme_code"] not in schemes.SCHEMES), None)
        detail = (strings["error_unknown_scheme"].format(row=row, code=cases[row - 1]["scheme_code"])
                  if row else str(exc))
        message = strings["error_upload_failed"].format(message=detail)
        return JSONResponse(status_code=400, content={"error": message})
    for case_data, questions in prepared:
        import_case(store, record=case_data["record"], scheme_code=case_data["scheme_code"],
                    questions=questions, language=settings.language)
    return {"imported": len(prepared)}


def _place_call(case_id: str, live: bool, farmer_name: str, scenario: str = "confirmed") -> None:
    case = store.get_case(case_id)
    if case is None:
        return
    questions = schemes.questions_for(case["scheme_code"], case["language"])
    try:
        if live:
            provider = build_call_provider("call-e", api_key=settings.calle_api_key)
            phone = settings.demo_phone_number
        else:
            from .call_adapter import DemoCallProvider, CallOutcome
            answers = dict(ANSWERS_BY_FIELD)
            if scenario == "uncertain":
                for f in schemes.get_scheme(case["scheme_code"]).fields:
                    answers[f.name] = (("so knapp 43 ungefähr" if case["language"] == "de" else "about 43") if f.kind == "number"
                                       else ("vielleicht, ich glaube schon" if case["language"] == "de" else "maybe, I think so"))
            provider = DemoCallProvider(answers if scenario != "unreachable" else {}, consent=scenario != "refused")
            if scenario == "configuration":
                class ConfigurationDemo:
                    def collect(self, **kwargs):
                        return CallOutcome(outcome="failed", failure_code="insufficient_balance")
                provider = ConfigurationDemo()
            phone = "+49000000000"
        outcome = run_call(store, case_id=case_id, provider=provider, farmer_name=farmer_name,
                 phone=phone, questions=questions, reserved=True,
                 record_agent=None if live else RecordAgent())
        if case["case_kind"] == "support":
            if outcome.outcome == "completed":
                store.set_goal_step(case_id, "evidence_captured")
                store.set_goal_step(case_id, "human_review")
            else:
                store.route_to_expert(case_id, reason=f"Callback outcome: {outcome.outcome}",
                                      question="Please decide the next safe step; no automatic redial is made.")
    except Exception:  # noqa: BLE001 - already recorded as call_failed in the log
        if store.get_case(case_id)["status"] == CALL_IN_PROGRESS:
            store.append(case_id, "call_configuration_error", payload={"failure_code": "initialization_failed"})
            store.set_status(case_id, NEEDS_INFORMATION)


@app.post("/api/cases/{case_id}/call")
def start_call(case_id: str, body: CallRequest, background: BackgroundTasks) -> dict:
    case = store.get_case(case_id)
    if case is None:
        raise HTTPException(404, ui_strings(settings.language)["error_case_not_found"])
    if case["status"] in (CALL_IN_PROGRESS, CLOSED):
        raise HTTPException(409, "This case is calling or already closed")
    questions = schemes.questions_for(case["scheme_code"], case["language"])
    missing = find_missing(case["original_record"], questions)
    if not missing:
        raise HTTPException(409, "No missing information to call about")
    if body.live:
        if not settings.has_calle:
            raise HTTPException(400, "CALLE_API_KEY is not configured")
        if not settings.demo_phone_number:
            raise HTTPException(400, "DEMO_PHONE_NUMBER is not configured")
    try:
        store.begin_call(case_id, payload={"farmer": body.farmer_name, "language": case["language"],
                                          "fields": missing, "provider": "call-e" if body.live else "demo"})
    except ValueError as exc:
        raise HTTPException(409, "A call is already in progress or the case is closed") from exc
    background.add_task(_place_call, case_id, body.live, body.farmer_name, body.scenario)
    return {"started": True, "case_id": case_id, "live": body.live}


@app.post("/api/support-goals/{case_id}/callback")
def support_callback(case_id: str, body: CallRequest, background: BackgroundTasks) -> dict:
    case = store.get_case(case_id)
    if case is None or case["case_kind"] != "support":
        raise HTTPException(404, "Support goal not found")
    if case["goal_step"] != "awaiting_callback":
        raise HTTPException(409, "This support goal is not awaiting a callback")
    # Delegate reservation and safety validation to the established call path.
    return start_call(case_id, body, background)


@app.post("/api/cases/{case_id}/review")
def review(case_id: str, body: ReviewRequest) -> dict:
    """Approve fields already present in the log. This endpoint never calls anyone."""
    case = store.get_case(case_id)
    if case is None:
        raise HTTPException(404, ui_strings(settings.language)["error_case_not_found"])
    if not store.events(case_id, kind="answer_captured"):
        raise HTTPException(409, "No call evidence for this case yet - place a call first")
    try:
        result = review_case(store, case_id=case_id, approved_fields=set(body.approved_fields),
                             reviewer=body.reviewer, notes=body.notes)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return export_correction_package(store, case_id, result)


@app.post("/api/support-goals/{case_id}/review")
def review_support_goal(case_id: str, body: ReviewRequest) -> dict:
    case = store.get_case(case_id)
    if case is None or case["case_kind"] != "support":
        raise HTTPException(404, "Support goal not found")
    if case["goal_step"] != "human_review":
        raise HTTPException(409, "This support goal is not ready for human review")
    result = review_case(store, case_id=case_id, approved_fields=set(body.approved_fields),
                         reviewer=body.reviewer, notes=body.notes)
    store.set_goal_step(case_id, "exported")
    return export_correction_package(store, case_id, result)


@app.post("/api/support-goals/{case_id}/route")
def route_support_goal(case_id: str, body: ExpertRouteRequest) -> dict:
    try:
        store.route_to_expert(case_id, reason=body.reason, question=body.question, assignee=body.assignee)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return case_detail(case_id)


@app.get("/api/cases/{case_id}/export.{format}")
def download_package(case_id: str, format: Literal["csv", "json"]) -> Response:
    try:
        package = export_correction_package(store, case_id)
    except KeyError as exc:
        raise HTTPException(404, "Case not found") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    content = io.correction_csv(package) if format == "csv" else io.correction_json(package)
    return Response(content, media_type="text/csv" if format == "csv" else "application/json",
                    headers={"Content-Disposition": f'attachment; filename="{case_id}-corrections.{format}"'})


@app.post("/api/cases/{case_id}/language")
def set_call_language(case_id: str, body: LanguageRequest) -> dict:
    """The language the farmer is called in, independent of the console language."""
    if body.language not in SUPPORTED:
        raise HTTPException(400, f"Unsupported language {body.language!r}")
    case = store.get_case(case_id)
    if case is None:
        raise HTTPException(404, ui_strings(settings.language)["error_case_not_found"])
    if case["status"] in (CALL_IN_PROGRESS, CLOSED):
        raise HTTPException(409, "Call language is locked while calling or after closure")
    with store._lock:
        store._conn.execute("UPDATE cases SET language = ? WHERE case_id = ?", (body.language, case_id))
        store._conn.commit()
    store.append(case_id, "call_language_changed", payload={"language": body.language})
    return case_detail(case_id)


@app.get("/api/i18n/{language}")
def i18n(language: str) -> dict:
    """Console strings. The console language never changes what the farmer hears."""
    if language not in SUPPORTED:
        raise HTTPException(400, f"Unsupported language {language!r}")
    # Field labels are console chrome, so they follow the console language and
    # come from every scheme a case in the queue might use.  The question the
    # farmer was actually asked is evidence and is never re-translated.
    field_labels: dict[str, str] = {}
    for code in schemes.SCHEMES:
        field_labels.update(schemes.labels_for(code, language))
    return {**ui_strings(language), "field_labels": field_labels,
            "field_reasons": {f.name: f.why[language] for s in schemes.SCHEMES.values() for f in s.fields},
            "schemes": {s.code: {"code": s.code, "name": s.name[language], "programme": s.programme[language],
                                 "summary": s.summary[language], "payment": s.payment[language], "source": s.source}
                        for s in schemes.SCHEMES.values()}}


@app.get("/api/config")
def config() -> dict:
    """What the console may offer, without exposing any secret."""
    return {"live_calls_available": bool(settings.has_calle and settings.demo_phone_number),
            "languages": list(SUPPORTED),
            "default_console_language": settings.language,
            "default_call_language": settings.language}


def main() -> None:
    import uvicorn

    print("AcreVoice adviser console on http://127.0.0.1:8080")
    uvicorn.run(app, host="127.0.0.1", port=8080, log_level="warning")


if __name__ == "__main__":
    main()
