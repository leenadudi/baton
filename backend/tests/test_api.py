import pytest
from fastapi.testclient import TestClient

from app import state
from app.main import app


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    state.reset()
    yield


client = TestClient(app)


def patient(pid):
    resp = client.get(f"/patients/{pid}")
    assert resp.status_code == 200
    return resp.json()


def test_list_patients():
    resp = client.get("/patients")
    assert resp.status_code == 200
    patients = resp.json()
    assert len(patients) == 6
    p1 = next(p for p in patients if p["id"] == "p1")
    ids = {i["id"] for i in p1["issues"]}
    assert {"p1:conflict:anticoagulation", "p1:conflict:weight_bearing",
            "p1:conflict:destination", "p1:handoff:followUpOwner",
            "p1:handoff:pend:Type and screen", "p1:blocker:b1",
            "p1:blocker:b2"} <= ids
    p6 = next(p for p in patients if p["id"] == "p6")
    assert p6["issues"] == []
    for p in patients:
        for n in p["notes"]:
            for tag in n["tags"]:
                assert isinstance(tag, list) and len(tag) == 2


def test_unknown_patient_404():
    assert client.get("/patients/nope").status_code == 404


def test_add_note_and_adopt():
    resp = client.post("/patients/p6/notes",
                       json={"role": "Surgery", "topic": "diet", "value": "NPO"})
    assert resp.status_code == 200
    ids = {i["id"] for i in resp.json()["issues"]}
    assert "p6:conflict:diet" in ids
    resp = client.patch("/issues/p6:conflict:diet",
                        json={"action": "adopt", "value": "NPO"})
    assert resp.status_code == 200
    ids = {i["id"] for i in resp.json()["issues"]}
    assert "p6:conflict:diet" not in ids


def test_fill_handoff_field():
    resp = client.patch("/issues/p2:handoff:codeStatus",
                        json={"action": "fill", "value": "Full code"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["handoff"]["codeStatus"] == "Full code"
    assert "p2:handoff:codeStatus" not in {i["id"] for i in body["issues"]}


def test_clear_and_escalate():
    resp = client.patch("/issues/p1:blocker:b1", json={"action": "clear"})
    assert resp.status_code == 200
    assert "p1:blocker:b1" not in {i["id"] for i in resp.json()["issues"]}
    resp = client.patch("/issues/p1:blocker:b2", json={"action": "escalate"})
    assert resp.status_code == 200
    b2 = next(i for i in resp.json()["issues"] if i["id"] == "p1:blocker:b2")
    assert b2["escalated"] is True


def test_assign_owner_shows_in_brief():
    resp = client.patch("/issues/p1:conflict:anticoagulation",
                        json={"action": "owner", "value": "Night Resident"})
    assert resp.status_code == 200
    issue = next(i for i in resp.json()["issues"]
                 if i["id"] == "p1:conflict:anticoagulation")
    assert issue["owner"] == "Night Resident"
    brief = client.get("/brief").text
    assert "Owner: Night Resident" in brief


def test_brief_shape():
    brief = client.get("/brief").text
    assert brief.startswith("SHIFT HANDOFF BRIEF")
    assert "open coordination issues" in brief
    items = [line for line in brief.splitlines()
             if line and line[0].isdigit() and "[" in line]
    assert items and "[HIGH]" in items[0]
    assert len(items) <= 14
    total = sum(len(p["issues"]) for p in client.get("/patients").json())
    if total > 14:
        assert f"+ {total - 14} lower-priority items in Baton." in brief


def test_note_validation():
    assert client.post("/patients/p1/notes", json={"role": "Nursing"}).status_code == 422
    resp = client.post("/patients/p1/notes",
                       json={"role": "Nursing", "topic": "bogus", "value": "x"})
    assert resp.status_code == 422


def test_demo_reset():
    client.patch("/issues/p2:handoff:codeStatus",
                 json={"action": "fill", "value": "Full code"})
    assert client.post("/demo/reset").json() == {"status": "ok"}
    ids = {i["id"] for i in patient("p2")["issues"]}
    assert "p2:handoff:codeStatus" in ids
