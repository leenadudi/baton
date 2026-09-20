import pytest
from fastapi.testclient import TestClient

from app import state, suggest
from app.main import app


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PANEL_SOURCE", "demo")
    state.reset_all()
    yield


client = TestClient(app)


def patients():
    resp = client.get("/patients")
    assert resp.status_code == 200
    return resp.json()


def find_issue(kind, pred=None):
    for p in patients():
        for i in p["issues"]:
            if i["type"] == kind and (pred is None or pred(i)):
                return p, i
    raise AssertionError(f"no {kind} issue found")


def fake_ask(payload):
    async def _fake(system, user):
        return payload
    return _fake


def test_clarify_returns_message(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(suggest, "_ask",
                        fake_ask({"message": "Drs disagree on diet — which stands?"}))
    _, issue = find_issue("conflict")
    resp = client.post("/suggest/clarify", json={"issue_id": issue["id"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["advisory"] is True
    assert body["message"].startswith("Drs disagree")


def test_clarify_wrong_type_400():
    _, issue = find_issue("blocker")
    resp = client.post("/suggest/clarify", json={"issue_id": issue["id"]})
    assert resp.status_code == 400


def test_owner_outside_allowed_is_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(suggest, "_ask",
                        fake_ask({"owner": "The Moon", "reason": "because"}))
    _, issue = find_issue("blocker")
    resp = client.post("/suggest/owner", json={"issue_id": issue["id"]})
    assert resp.status_code == 200
    assert resp.json()["owner"] is None


def test_owner_valid(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(suggest, "_ask",
                        fake_ask({"owner": "Case Management", "reason": "Auth item."}))
    _, issue = find_issue("blocker")
    resp = client.post("/suggest/owner", json={"issue_id": issue["id"]})
    assert resp.json()["owner"] == "Case Management"
    # pending-result issues are also valid targets
    _, pend = find_issue("handoff",
                         lambda i: i.get("fix", {}).get("kind") == "pending")
    resp = client.post("/suggest/owner", json={"issue_id": pend["id"]})
    assert resp.status_code == 200


def test_field_bad_index_drops_value(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(suggest, "_ask",
                        fake_ask({"value": "DNR", "noteIndex": 99, "quote": "x"}))
    p, issue = find_issue("handoff",
                          lambda i: i.get("fix", {}).get("kind") == "field")
    resp = client.post("/suggest/field", json={"issue_id": issue["id"]})
    assert resp.status_code == 200
    assert resp.json()["value"] is None
    assert resp.json()["source"] is None


def test_field_valid_index_and_verbatim_quote(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    p, issue = find_issue("handoff",
                          lambda i: i.get("fix", {}).get("kind") == "field")
    full = client.get(f"/patients/{p['id']}").json()
    note = full["notes"][0]
    quote = note["text"][:20]
    monkeypatch.setattr(suggest, "_ask",
                        fake_ask({"value": "from notes", "noteIndex": 0,
                                  "quote": quote}))
    resp = client.post("/suggest/field", json={"issue_id": issue["id"]})
    body = resp.json()
    assert body["value"] == "from notes"
    assert body["source"]["text"] == note["text"]

    # quote NOT in the note -> drop everything
    monkeypatch.setattr(suggest, "_ask",
                        fake_ask({"value": "from notes", "noteIndex": 0,
                                  "quote": "ZZZ not in note"}))
    resp = client.post("/suggest/field", json={"issue_id": issue["id"]})
    assert resp.json()["value"] is None


def test_field_wrong_type_400():
    _, issue = find_issue("conflict")
    assert client.post("/suggest/field",
                       json={"issue_id": issue["id"]}).status_code == 400


def test_huddle_returns_script(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(suggest, "_ask",
                        fake_ask({"script": "Room by room: ..."}))
    resp = client.post("/suggest/huddle")
    assert resp.status_code == 200
    assert resp.json() == {"advisory": True, "script": "Room by room: ..."}


def test_no_key_is_503():
    _, issue = find_issue("conflict")
    resp = client.post("/suggest/clarify", json={"issue_id": issue["id"]})
    assert resp.status_code == 503
