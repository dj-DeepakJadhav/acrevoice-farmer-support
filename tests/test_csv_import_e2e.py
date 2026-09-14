"""End-to-end verification of the CSV import workflow against the checked-in
Bavarian sample dataset (``data/sample_import.csv``).

This exercises the same seven attack angles as the manual QA pass:

1. the CSV imports cleanly and every scheme code is recognised
2. imported cases populate ``GET /api/cases`` with correct summary fields,
   sorted by urgency
3. scheme labels/why-text on ``GET /api/cases/{id}`` are in German and the
   missing fields are correctly identified
4. a full demo call records evidence in the audit log and can be reviewed
5. the exported correction package carries original/proposed/question/
   confirmation/timestamp per changed field
6. edge cases (duplicate upload, unknown scheme code, all-blank row, a row
   that already has every field filled) do not crash and do not silently
   corrupt the queue
7. a full adviser session (queue -> case -> why -> call -> review -> export)
   reads as a coherent, German-language story

Nothing here places a live call: every call in this file goes through
``DemoCallProvider`` via ``POST /api/cases/{id}/call`` with ``"live": false``
(the default), never ``CalleCallProvider``.

The expected-data tables below were derived by hand from
``data/sample_import.csv`` and cross-checked against ``acrevoice/schemes.py``'s
field lists with a throwaway ``io.record_from_csv`` run - see
``test_hand_derived_expectations_match_the_csv_on_disk`` below, which fails
loudly if the fixture is edited without updating this file.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from acrevoice import io as acrevoice_io
from acrevoice import schemes
from acrevoice.sample_case import ANSWERS_BY_FIELD
from acrevoice.store import AuditStore
from acrevoice.workflow import find_missing

SAMPLE_CSV = Path(__file__).resolve().parents[1] / "data" / "sample_import.csv"

# holding_name -> (scheme_code, expected missing field names), for rows that
# have at least one blank field relevant to their own scheme.
EXPECTED_ROWS = {
    "Müller Ökohof GmbH, München": ("OER2", {"hauptfruchtarten"}),
    "Mayr Landwirtschaft KG, Augsburg": ("OER2", {"leguminosen_anteil"}),
    "Gruber Ackerbau GbR, Regensburg": ("OER2", {"hauptfruchtarten", "leguminosen_anteil"}),
    "Weber Agrarhof, Passau": ("GLOEZ6", {"bodenbedeckung_art"}),
    "Schneider Hof GbR, Bamberg": ("GLOEZ6", {"bedeckung_zeitraum_eingehalten"}),
    "Huber Landwirtschaft, Würzburg": ("GLOEZ6", {"bodenbedeckung_art", "bedeckung_zeitraum_eingehalten"}),
    "Wagner Gemischtbetrieb, Augsburg": ("GLOEZ8", {"brache_ha"}),
    "Krüger Ackerbau eG, Regensburg": ("GLOEZ8", {"landschaftselemente"}),
    "Lang Hofgut, Rosenheim": ("GLOEZ8", {"brache_ha", "landschaftselemente"}),
    "Krauss Weidehof, Bamberg": ("OER4", {"rgv_je_hektar"}),
    "Böhm Alpwirtschaft GbR, Würzburg": ("OER4", {"rgv_je_hektar"}),
    "Reiter Ökolandbau GbR, Passau": ("OER2", {"leguminosen_anteil"}),
    "Vogt Agrarhof, Bamberg": ("GLOEZ6", {"bodenbedeckung_art"}),
    "Sailer Landwirtschaft eG, Regensburg": ("GLOEZ8", {"landschaftselemente"}),
    "Brandt Weidehof, Rosenheim": ("OER4", {"rgv_je_hektar"}),
    "Kastner Blühwiesenhof, München": ("OER1B", {"bluehmischung_art"}),
}

# Rows that arrive with every one of their own scheme's fields already filled
# in the CSV - nothing missing, nothing to call about.
COMPLETE_ROWS = {
    "Bauer Feldwirtschaft eG, Rosenheim": "OER2",
    "Fuchs Biohof KG, München": "GLOEZ6",
    "Meier Landwirtschaft GmbH, Passau": "GLOEZ8",
    "Hoffmann Grünlandbetrieb, München": "OER4",
    "Hartmann Grünlandbetrieb GmbH, Augsburg": "OER4",
}

TOTAL_ROWS = len(EXPECTED_ROWS) + len(COMPLETE_ROWS)


@pytest.fixture()
def client():
    from acrevoice import server as server_module

    with tempfile.TemporaryDirectory() as tmp:
        test_store = AuditStore(Path(tmp) / "test.db")
        server_module.store = test_store
        with TestClient(server_module.app) as c:
            yield c
        test_store.close()


def _upload_sample(client) -> dict:
    with SAMPLE_CSV.open("rb") as fh:
        return client.post(
            "/api/import/csv",
            files={"file": ("sample_import.csv", fh, "text/csv")},
        )


def test_hand_derived_expectations_match_the_csv_on_disk():
    """Guard against this file silently going stale if the fixture changes."""
    with SAMPLE_CSV.open("rb") as fh:
        cases = acrevoice_io.record_from_csv(fh)
    assert len(cases) == TOTAL_ROWS, (
        f"data/sample_import.csv now has {len(cases)} rows; this test file's "
        f"EXPECTED_ROWS/COMPLETE_ROWS tables assume {TOTAL_ROWS} and need updating"
    )
    by_name = {c["record"]["holding_name"]: c for c in cases}
    assert set(by_name) == set(EXPECTED_ROWS) | set(COMPLETE_ROWS)
    for holding_name, (scheme_code, missing_fields) in EXPECTED_ROWS.items():
        record = by_name[holding_name]["record"]
        questions = schemes.questions_for(scheme_code, "de")
        assert set(find_missing(record, questions)) == missing_fields
    for holding_name, scheme_code in COMPLETE_ROWS.items():
        record = by_name[holding_name]["record"]
        questions = schemes.questions_for(scheme_code, "de")
        assert find_missing(record, questions) == []


# -- 1. clean import, recognised scheme codes --------------------------------

def test_sample_csv_is_present_and_shaped_as_expected():
    assert SAMPLE_CSV.exists(), f"expected fixture at {SAMPLE_CSV}"
    text = SAMPLE_CSV.read_text(encoding="utf-8-sig")
    header = text.splitlines()[0].split(",")
    assert {"holding_id", "holding_name", "application_year", "scheme_code"} <= set(header)


def test_sample_csv_imports_cleanly_with_recognized_scheme_codes(client):
    resp = _upload_sample(client)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"imported": TOTAL_ROWS}

    cases = client.get("/api/cases").json()
    assert len(cases) == TOTAL_ROWS
    scheme_codes = {c["scheme"]["code"] for c in cases}
    all_codes = {code for code, _ in EXPECTED_ROWS.values()} | set(COMPLETE_ROWS.values())
    expected_codes = {schemes.get_scheme(code).code for code in all_codes}
    assert scheme_codes == expected_codes


# -- 2. queue population -------------------------------------------------------

def test_imported_cases_populate_the_queue_with_correct_summary_fields(client):
    _upload_sample(client)
    cases = client.get("/api/cases").json()
    assert len(cases) == TOTAL_ROWS

    by_holding = {c["holding_name"]: c for c in cases}
    assert set(by_holding) == set(EXPECTED_ROWS) | set(COMPLETE_ROWS)

    for holding_name, (scheme_code, missing_fields) in EXPECTED_ROWS.items():
        case = by_holding[holding_name]
        assert case["scheme"]["code"] == schemes.get_scheme(scheme_code).code
        assert case["missing_count"] == len(missing_fields)
        assert case["application_year"] in {"2025", "2026"}
        # nothing has been called yet: no case should already claim confirmed answers
        assert case["confirmed_count"] == 0
        assert case["status"] == "needs_information"

    for holding_name, scheme_code in COMPLETE_ROWS.items():
        case = by_holding[holding_name]
        assert case["missing_count"] == 0
        assert case["confirmed_count"] == 0


def test_queue_is_sorted_by_urgency(client):
    _upload_sample(client)
    cases = client.get("/api/cases").json()
    order = {"needs_follow_up": 0, "needs_information": 1, "call_in_progress": 2,
             "awaiting_review": 3, "closed": 4}
    statuses = [order[c["status"]] for c in cases]
    assert statuses == sorted(statuses)


# -- 3. localisation + missing-field detection --------------------------------

def test_case_detail_shows_german_labels_why_text_and_missing_fields(client):
    _upload_sample(client)
    cases = client.get("/api/cases").json()
    gruber = next(c for c in cases if c["holding_name"] == "Gruber Ackerbau GbR, Regensburg")
    detail = client.get(f"/api/cases/{gruber['case_id']}").json()

    assert detail["language"] == "de"
    assert set(detail["missing_fields"]) == EXPECTED_ROWS["Gruber Ackerbau GbR, Regensburg"][1]

    scheme = schemes.get_scheme("OER2")
    fields_by_name = {f["name"]: f for f in detail["fields"]}
    assert set(fields_by_name) == {f.name for f in scheme.fields}
    for scheme_field in scheme.fields:
        rendered = fields_by_name[scheme_field.name]
        assert rendered["label"] == scheme_field.label["de"]
        assert rendered["why"] == scheme_field.why["de"]
        # spot-check this is genuinely German prose, not an English fallback
        assert rendered["why"] != scheme_field.why["en"]


# -- 4. full call workflow -----------------------------------------------------

def test_full_call_workflow_records_evidence_and_reviews(client):
    from acrevoice import server as server_module

    _upload_sample(client)
    cases = client.get("/api/cases").json()
    krauss = next(c for c in cases if c["holding_name"] == "Krauss Weidehof, Bamberg")
    case_id = krauss["case_id"]
    assert krauss["missing_count"] == 1

    started = client.post(f"/api/cases/{case_id}/call", json={"live": False})
    assert started.status_code == 200
    assert started.json() == {"started": True, "case_id": case_id, "live": False}

    # audit log carries the answer, independent of the API response shape
    answer_events = server_module.store.events(case_id, kind="answer_captured")
    assert len(answer_events) == 1
    assert answer_events[0].field == "rgv_je_hektar"
    assert answer_events[0].payload["confirmed"] is True
    assert answer_events[0].payload["answer"] == ANSWERS_BY_FIELD["rgv_je_hektar"]

    detail = client.get(f"/api/cases/{case_id}").json()
    assert detail["status"] == "awaiting_review"
    assert detail["confirmed_fields"] == ["rgv_je_hektar"]
    assert len(detail["answers"]) == 1
    answer = detail["answers"][0]
    assert answer["confirmed"] is True
    assert answer["question"]  # the scheme's own German question, not blank

    reviewed = client.post(
        f"/api/cases/{case_id}/review",
        json={"approved_fields": detail["confirmed_fields"], "reviewer": "Tester"},
    )
    assert reviewed.status_code == 200
    package = reviewed.json()
    assert package["case_id"] == case_id

    # source record is untouched by the whole flow
    case_row = server_module.store.get_case(case_id)
    assert case_row["original_record"]["rgv_je_hektar"] == ""
    assert package["original_record"]["rgv_je_hektar"] == ""
    assert package["record"]["rgv_je_hektar"] == ANSWERS_BY_FIELD["rgv_je_hektar"]

    final = client.get(f"/api/cases/{case_id}").json()
    assert final["status"] == "closed"


# -- 5. export shape ------------------------------------------------------------

def test_correction_package_carries_structured_evidence_per_field(client):
    _upload_sample(client)
    cases = client.get("/api/cases").json()
    wagner = next(c for c in cases if c["holding_name"] == "Wagner Gemischtbetrieb, Augsburg")
    case_id = wagner["case_id"]

    client.post(f"/api/cases/{case_id}/call", json={"live": False})
    detail = client.get(f"/api/cases/{case_id}").json()
    confirmed = detail["confirmed_fields"]
    assert confirmed, "demo answers should confirm brache_ha for GLOEZ8"

    package = client.post(
        f"/api/cases/{case_id}/review",
        json={"approved_fields": confirmed, "reviewer": "Tester"},
    ).json()

    assert package["changes"], "expected at least one applied change"
    for change in package["changes"]:
        assert set(change) == {"field", "original", "proposed", "confirmed", "question", "captured_at"}
        assert change["confirmed"] is True
        assert change["original"] == ""  # every changed field here started blank
        assert change["proposed"]
        assert change["question"]
        assert change["captured_at"]

    # the review response itself is a structured object, not merely a wrapper
    # around one opaque blob: case identity, record, changes and evidence
    # timeline are all separately addressable fields.
    assert set(package) == {
        "case_id", "holding_id", "application_year", "language", "status",
        "record", "original_record", "changes", "not_applied_unconfirmed",
        "review", "evidence_timeline",
    }
    assert package["evidence_timeline"]  # real timeline entries, not empty


# -- 6. edge cases --------------------------------------------------------------

def test_uploading_the_same_csv_twice_does_not_error_but_does_not_dedupe(client):
    """Documents current behaviour: re-importing an identical batch creates a
    second, independent set of cases per holding rather than being rejected or
    deduplicated. Nothing in the API contract promises idempotent import, but
    an adviser who double-clicks "import" (or re-uploads after a UI hiccup)
    will silently end up with two live cases per holding and no warning.
    """
    first = _upload_sample(client)
    second = _upload_sample(client)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == {"imported": TOTAL_ROWS}

    cases = client.get("/api/cases").json()
    assert len(cases) == TOTAL_ROWS * 2
    case_ids = {c["case_id"] for c in cases}
    assert len(case_ids) == TOTAL_ROWS * 2  # distinct cases, no accidental id collision

    mueller_cases = [c for c in cases if c["holding_name"] == "Müller Ökohof GmbH, München"]
    assert len(mueller_cases) == 2


def test_unknown_scheme_code_is_rejected_before_any_row_is_imported(client):
    from acrevoice import server as server_module

    csv_text = (
        "holding_id,holding_name,application_year,scheme_code,hauptfruchtarten,leguminosen_anteil\n"
        "BY-00001,Gut Erste,2026,OER2,,15\n"
        "BY-00002,Gut Zweite,2026,GLOEZ6,,\n"
        "BY-00003,Gut Unbekannt,2026,NOPE99,,\n"
    )
    resp = client.post(
        "/api/import/csv",
        files={"file": ("bad.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")},
    )
    assert resp.status_code == 400
    assert "NOPE99" in resp.text or "Unknown scheme" in resp.text

    # rows 1 and 2 came before the bad row and are perfectly valid on their
    # own; the endpoint's own docstring promises they must not be imported.
    assert server_module.store.list_cases() == []


def test_all_blank_data_row_still_creates_a_case_with_every_field_missing(client):
    csv_text = (
        "holding_id,holding_name,application_year,scheme_code,hauptfruchtarten,leguminosen_anteil\n"
        "BY-99999,,,OER2,,\n"
    )
    resp = client.post(
        "/api/import/csv",
        files={"file": ("blank.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")},
    )
    assert resp.status_code == 200
    assert resp.json() == {"imported": 1}

    cases = client.get("/api/cases").json()
    assert len(cases) == 1
    case = cases[0]
    assert case["holding_id"] == "BY-99999"
    assert case["holding_name"] == ""
    assert case["status"] == "needs_information"
    assert case["missing_count"] == 2

    detail = client.get(f"/api/cases/{case['case_id']}").json()
    assert set(detail["missing_fields"]) == {"hauptfruchtarten", "leguminosen_anteil"}


def test_malformed_upload_is_a_400_not_a_crash(client):
    resp = client.post(
        "/api/import/csv",
        files={"file": ("bad.csv", io.BytesIO(b"\xff\xfe\x00not-utf8"), "text/csv")},
    )
    assert resp.status_code == 400


def test_complete_import_is_closed_and_cannot_place_an_empty_call(client):
    from acrevoice import server as server_module
    _upload_sample(client)
    case = next(c for c in client.get("/api/cases").json()
                if c["holding_name"] == "Bauer Feldwirtschaft eG, Rosenheim")
    assert case["missing_count"] == 0
    assert case["status"] == "closed"
    assert client.post(f"/api/cases/{case['case_id']}/call", json={"live": False}).status_code == 409
    assert server_module.store.events(case["case_id"], kind="call_started") == []


# -- 7. adviser session narrative ----------------------------------------------

def test_adviser_session_walkthrough_import_to_export(client):
    """Load queue -> open a case -> read the scheme's why-text -> place a call
    -> review -> export, reading as a coherent German-language session.
    """
    imported = _upload_sample(client)
    assert imported.json()["imported"] == TOTAL_ROWS

    queue = client.get("/api/cases").json()
    assert queue, "queue must not be empty after import"

    weber = next(c for c in queue if c["holding_name"] == "Weber Agrarhof, Passau")
    detail = client.get(f"/api/cases/{weber['case_id']}").json()
    assert detail["scheme"]["name"]  # German scheme name shown to the adviser
    missing_field = detail["missing_fields"][0]
    field_meta = next(f for f in detail["fields"] if f["name"] == missing_field)
    assert field_meta["why"], "an adviser must be able to justify the call"

    call = client.post(f"/api/cases/{weber['case_id']}/call", json={"live": False})
    assert call.status_code == 200

    after_call = client.get(f"/api/cases/{weber['case_id']}").json()
    assert after_call["status"] in {"awaiting_review", "needs_follow_up"}
    if not after_call["confirmed_fields"]:
        pytest.skip("demo answers did not confirm any field for this scheme")

    package = client.post(
        f"/api/cases/{weber['case_id']}/review",
        json={"approved_fields": after_call["confirmed_fields"], "reviewer": "Beraterin Nguyen"},
    ).json()
    assert package["review"]["reviewer"] == "Beraterin Nguyen"
    assert package["status"] == "closed"
