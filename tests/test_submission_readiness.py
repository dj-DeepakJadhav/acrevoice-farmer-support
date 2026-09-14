"""Regression checks for the trust boundaries exposed during submission review."""
import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from acrevoice import server
from acrevoice.agent import RecordAgent
from acrevoice.call_adapter import CalleCallProvider, DemoCallProvider
from acrevoice.store import AuditStore
from acrevoice.workflow import confirmed_answers, import_case, review_case, run_call


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = AuditStore(tmp_path / "test.db")
    monkeypatch.setattr(server, "store", store)
    with TestClient(server.app) as client:
        yield client
    store.close()


def case_id(client):
    return next(c["case_id"] for c in client.get("/api/cases").json() if c["missing_count"])


def test_download_is_saved_review_only_and_survives_new_client(client):
    cid = case_id(client)
    assert client.get(f"/api/cases/{cid}/export.csv").status_code == 409
    client.post(f"/api/cases/{cid}/call", json={})
    detail = client.get(f"/api/cases/{cid}").json()
    approved = client.post(f"/api/cases/{cid}/review", json={"approved_fields": detail["confirmed_fields"]})
    assert approved.status_code == 200
    with TestClient(server.app) as fresh:
        downloaded = fresh.get(f"/api/cases/{cid}/export.json")
        assert downloaded.json() == approved.json()
        rows = list(csv.DictReader(io.StringIO(fresh.get(f"/api/cases/{cid}/export.csv").text)))
        assert len(rows) == len(approved.json()["changes"])
        assert all(row["question"] for row in rows)
        assert "attachment" in downloaded.headers["content-disposition"]
        assert fresh.post(f"/api/cases/{cid}/review", json={"approved_fields": []}).status_code == 409
        assert fresh.post(f"/api/cases/{cid}/call", json={}).status_code == 409
        assert fresh.post(f"/api/cases/{cid}/language", json={"language": "en"}).status_code == 409


@pytest.mark.parametrize("scenario,action", [("uncertain", "follow_up"), ("refused", "refused"),
                                           ("configuration", "configuration")])
def test_demo_failure_states_have_distinct_next_actions(client, scenario, action):
    cid = case_id(client)
    client.post(f"/api/cases/{cid}/call", json={"scenario": scenario})
    detail = client.get(f"/api/cases/{cid}").json()
    assert detail["next_action"] == action
    assert detail["confirmed_fields"] == []
    assert detail["call_history"][-1]["provider"] == "demo"


@pytest.mark.parametrize("consent", [None, "true", "false", 1])
def test_provider_requires_explicit_boolean_consent(consent):
    provider = object.__new__(CalleCallProvider)
    call = {"structured_result": {"consent_given": consent, "area_ha": "43", "area_ha_confirmed": True}}
    outcome = provider._to_outcome(call, ["area_ha"], {}, "en")
    assert not outcome.answers


def test_string_false_is_never_confirmation():
    provider = object.__new__(CalleCallProvider)
    call = {"structured_result": {"consent_given": True, "area_ha": "43", "area_ha_confirmed": "false"}}
    assert not provider._to_outcome(call, ["area_ha"], {}, "en").answers[0].confirmed


def test_latest_unconfirmed_answer_revokes_old_confirmation(tmp_path):
    store = AuditStore(tmp_path / "test.db")
    questions = {"area_ha": "Area?"}
    cid = import_case(store, record={"area_ha": ""}, scheme_code="TEST", questions=questions)
    for value in ("42.5", "maybe 43"):
        run_call(store, case_id=cid, provider=DemoCallProvider({"area_ha": value}),
                 farmer_name="Synthetic", phone="unused", questions=questions, record_agent=RecordAgent())
    assert confirmed_answers(store, cid) == {}
    assert review_case(store, case_id=cid, approved_fields={"area_ha"}, reviewer="Test")["applied"] == []
    store.close()


def test_two_connections_cannot_reserve_same_call(tmp_path):
    stores = [AuditStore(tmp_path / "test.db") for _ in range(2)]
    cid = import_case(stores[0], record={"area_ha": ""}, scheme_code="TEST", questions={"area_ha": "Area?"})
    def reserve(store):
        try:
            store.begin_call(cid, payload={})
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(reserve, stores)) == [False, True]
    assert len(stores[0].events(cid, kind="call_started")) == 1
    for store in stores:
        store.close()


def test_malformed_csv_does_not_create_cases(client):
    for text in ("", "x,y\n1,2", "holding_id,holding_name,application_year,scheme_code\n1,A,2026,OER2,extra"):
        response = client.post("/api/import/csv", files={"file": ("bad.csv", text, "text/csv")})
        assert response.status_code == 400
        assert server.store.list_cases() == []


def test_demo_never_discovers_or_calls_a_live_model(client, monkeypatch):
    def fail():
        pytest.fail("offline demo attempted live model discovery")
    monkeypatch.setattr("acrevoice.agent.build_record_agent", fail)
    cid = case_id(client)
    assert client.post(f"/api/cases/{cid}/call", json={}).status_code == 200
    assert client.get(f"/api/cases/{cid}").json()["status"] != "call_in_progress"


def test_real_calle_sdk_create_and_poll_with_offline_transport():
    """Exercise the installed SDK and adapter together; no network or credits."""
    import httpx
    from calle import CalleClient
    requests = []
    def respond(request):
        requests.append(request)
        if request.method == "POST":
            assert request.url.path == "/v1/calls"
            body = json.loads(request.content)
            assert body["recipients"][0]["phones"] == ["+49000000000"]
            assert "consent_given" in body["recipient_result_schema"]["properties"]
            return httpx.Response(201, json={"id": "offline-contract", "status": "queued"})
        assert request.url.path == "/v1/calls/offline-contract"
        return httpx.Response(200, json={"id": "offline-contract", "status": "completed",
                                       "structured_result": {"consent_given": True, "area_ha": "42.5", "area_ha_confirmed": True}})
    with httpx.Client(base_url="https://api.heycall-e.com", transport=httpx.MockTransport(respond)) as http:
        provider = object.__new__(CalleCallProvider)
        provider._client = CalleClient(api_key="offline-test", http_client=http)
        result = provider.collect(farmer_name="Synthetic", phone="+49000000000", record={},
                                  missing_fields=["area_ha"], language="en", questions={"area_ha": "Area?"})
        assert result.outcome == "completed"
        assert result.answers[0].answer == "42.5"
        assert [r.method for r in requests] == ["POST", "GET"]
