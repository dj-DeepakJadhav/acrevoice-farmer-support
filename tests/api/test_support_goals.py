"""The Bavaria-first navigator must preserve evidence and never decide eligibility."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from acrevoice.store import AuditStore


@pytest.fixture()
def client():
    from acrevoice import server as server_module

    with tempfile.TemporaryDirectory() as tmp:
        test_store = AuditStore(Path(tmp) / "support.db")
        server_module.store = test_store
        with TestClient(server_module.app) as c:
            yield c
        test_store.close()


def test_source_cards_are_official_dated_and_not_an_eligibility_decision(client):
    response = client.get("/api/funding-sources?land=Bayern&topic=eco_scheme&language=de")
    assert response.status_code == 200
    body = response.json()
    card = body["sources"][0]
    assert {"source_id", "publisher", "url", "checked_at", "review_by", "scope", "guidance",
            "record_type", "document_date"} <= set(card)
    assert "keine Förderzusage" in card["guidance"]


def test_completed_callback_requires_human_review_before_export(client):
    created = client.post("/api/support-goals", json={"holding_name": "Hof Bauer"})
    assert created.status_code == 200
    detail = created.json()
    case_id = detail["case_id"]
    assert detail["support_goal"]["goal_step"] == "awaiting_callback"

    callback = client.post(f"/api/support-goals/{case_id}/callback", json={"live": False, "scenario": "confirmed"})
    assert callback.status_code == 200
    detail = client.get(f"/api/support-goals/{case_id}").json()
    assert detail["support_goal"]["goal_step"] == "human_review"
    assert detail["status"] == "awaiting_review"
    assert detail["confirmed_fields"]

    reviewed = client.post(f"/api/support-goals/{case_id}/review", json={
        "approved_fields": detail["confirmed_fields"], "reviewer": "Bavaria adviser",
    })
    assert reviewed.status_code == 200
    detail = client.get(f"/api/support-goals/{case_id}").json()
    assert detail["support_goal"]["goal_step"] == "exported"
    assert detail["status"] == "closed"


def test_uncertain_or_refused_callback_routes_to_a_person_without_redial(client):
    created = client.post("/api/support-goals", json={"holding_name": "Hof Weber"}).json()
    case_id = created["case_id"]
    response = client.post(f"/api/support-goals/{case_id}/callback", json={"scenario": "refused"})
    assert response.status_code == 200
    detail = client.get(f"/api/support-goals/{case_id}").json()
    assert detail["support_goal"]["goal_step"] == "expert_routing"
    assert detail["support_goal"]["expert_route"]["reason"] == "Callback outcome: refused"
    assert len([e for e in detail["timeline"] if e["event"] == "call_started"]) == 1
    assert client.post(f"/api/support-goals/{case_id}/callback", json={}).status_code == 409
