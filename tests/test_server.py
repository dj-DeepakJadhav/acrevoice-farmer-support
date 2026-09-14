"""Contract tests for the adviser console API (T3a).

Every case in the queue belongs to a CAP scheme, and the console reads its
question wording, field labels and why-it-matters text from ``schemes.py`` in
the case's own call language.  These tests exercise the API another agent is
building the console against, so the shape matters as much as the behaviour.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from acrevoice import schemes
from acrevoice.store import AuditStore

CASE_SUMMARY_KEYS = {
    "case_id", "holding_id", "holding_name", "application_year", "status",
    "language", "scheme", "missing_count", "confirmed_count", "last_activity",
}
SCHEME_KEYS = {"code", "name", "programme", "summary", "payment", "source"}
ANSWER_KEYS = {
    "field", "label", "question", "why", "spoken", "answer", "confirmed",
    "approximate", "note", "captured_at",
}
FIELD_KEYS = {"name", "label", "why", "kind", "original_value"}


@pytest.fixture()
def client():
    from acrevoice import server as server_module

    with tempfile.TemporaryDirectory() as tmp:
        test_store = AuditStore(Path(tmp) / "test.db")
        server_module.store = test_store
        with TestClient(server_module.app) as c:
            yield c
        test_store.close()


def test_list_cases_matches_the_contract_shape(client):
    cases = client.get("/api/cases").json()

    assert len(cases) >= 5
    holdings = {c["holding_id"] for c in cases}
    assert len(holdings) >= 3
    scheme_codes = {c["scheme"]["code"] for c in cases}
    assert scheme_codes == {s.code for s in schemes.SCHEMES.values()}

    for case in cases:
        assert set(case) == CASE_SUMMARY_KEYS
        assert set(case["scheme"]) == SCHEME_KEYS
        assert case["missing_count"] >= 0
        assert case["last_activity"]


def test_list_cases_sorts_follow_up_before_closed(client):
    cases = client.get("/api/cases").json()
    order = {"needs_follow_up": 0, "needs_information": 1, "call_in_progress": 2,
             "awaiting_review": 3, "closed": 4}
    statuses = [order[c["status"]] for c in cases]
    assert statuses == sorted(statuses)


def test_case_detail_has_scheme_localised_fields(client):
    cases = client.get("/api/cases").json()
    case_id = cases[0]["case_id"]
    detail = client.get(f"/api/cases/{case_id}").json()

    assert CASE_SUMMARY_KEYS <= set(detail)
    for key in ("missing_fields", "confirmed_fields", "answers", "fields", "timeline"):
        assert key in detail

    scheme = next(s for s in schemes.SCHEMES.values() if s.code == detail["scheme"]["code"])
    assert {f.name for f in scheme.fields} == {f["name"] for f in detail["fields"]}
    for field in detail["fields"]:
        assert set(field) == FIELD_KEYS
        scheme_field = scheme.field(field["name"])
        assert field["label"] == scheme_field.label[detail["language"]]
        assert field["why"] == scheme_field.why[detail["language"]]
        assert field["kind"] == scheme_field.kind


def test_call_then_review_flow_produces_a_correction_package(client):
    cases = client.get("/api/cases").json()
    case = next(c for c in cases if c["missing_count"] > 0)
    case_id = case["case_id"]

    started = client.post(f"/api/cases/{case_id}/call", json={"live": False})
    assert started.status_code == 200

    detail = client.get(f"/api/cases/{case_id}").json()
    assert detail["status"] in {"awaiting_review", "needs_follow_up"}
    for answer in detail["answers"]:
        assert set(answer) == ANSWER_KEYS

    confirmed = detail["confirmed_fields"]
    if not confirmed:
        pytest.skip("demo answers did not confirm any field for this scheme")

    reviewed = client.post(f"/api/cases/{case_id}/review",
                           json={"approved_fields": confirmed, "reviewer": "Tester"})
    assert reviewed.status_code == 200
    package = reviewed.json()
    assert package["case_id"] == case_id
    assert all(c["confirmed"] for c in package["changes"])


def test_i18n_field_labels_cover_every_scheme_field(client):
    body = client.get("/api/i18n/de").json()
    all_fields = {f.name for s in schemes.SCHEMES.values() for f in s.fields}
    assert all_fields <= set(body["field_labels"])
