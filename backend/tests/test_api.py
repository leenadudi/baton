import pytest
from fastapi.testclient import TestClient

from app import state
from app.main import app


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PANEL_SOURCE", "demo")
    state.reset_all()
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


def test_log_marks_ongoing_work_unresolved():
    """The Completed tab filters on `resolved` — clearing/filling/reconciling
    close something, but escalating a blocker raises its urgency instead of
    resolving it, and adding a note can introduce a new conflict rather than
    settle one. Neither should read as done."""
    client.patch("/issues/p1:blocker:b1", json={"action": "clear"})
    client.patch("/issues/p1:blocker:b2", json={"action": "escalate"})
    client.post("/patients/p1/notes", json={"role": "Nursing", "text": "Vitals stable."})
    log = {e["text"]: e["resolved"] for e in patient("p1")["log"]}
    assert log["Cleared blocker: SNF insurance authorization"] is True
    assert log["Escalated blocker: Ambulance transport not booked"] is False
    assert log["Added Nursing note"] is False


def test_reconciling_note_via_add_note_endpoint_is_resolved():
    """POST /patients/:id/notes also accepts reconcile=true (a second path to
    the same effect PATCH .../adopt has) — a tagged reconciling note genuinely
    clears a conflict and should read as resolved, unlike a plain note."""
    resp = client.post("/patients/p1/notes", json={
        "role": "Attending", "topic": "anticoagulation", "value": "hold",
        "text": "Reconciled: hold going forward.", "reconcile": True,
    })
    assert resp.status_code == 200
    log = {e["text"]: e["resolved"] for e in patient("p1")["log"]}
    assert log["Added Attending note (Anticoagulation: hold)"] is True

    # An untagged reconcile=true note has no topic to clear, so it has no
    # effect on any conflict and must not read as resolved.
    resp = client.post("/patients/p1/notes", json={
        "role": "Attending", "text": "Just a comment.", "reconcile": True,
    })
    assert resp.status_code == 200
    log = {e["text"]: e["resolved"] for e in patient("p1")["log"]}
    assert log["Added Attending note"] is False


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


JUDGE_A = {"X-Session-Id": "judge-a"}
JUDGE_B = {"X-Session-Id": "judge-b"}


def test_sessions_are_isolated():
    """One judge's mutation must not change another judge's panel."""
    client.patch("/issues/p1:blocker:b1", json={"action": "clear"}, headers=JUDGE_A)
    a = {i["id"] for i in client.get("/patients/p1", headers=JUDGE_A).json()["issues"]}
    b = {i["id"] for i in client.get("/patients/p1", headers=JUDGE_B).json()["issues"]}
    default = {i["id"] for i in patient("p1")["issues"]}
    assert "p1:blocker:b1" not in a
    assert "p1:blocker:b1" in b
    assert "p1:blocker:b1" in default


def test_reset_only_clears_own_session():
    client.patch("/issues/p1:blocker:b1", json={"action": "clear"}, headers=JUDGE_A)
    client.patch("/issues/p1:blocker:b2", json={"action": "clear"}, headers=JUDGE_B)
    client.post("/demo/reset", headers=JUDGE_A)
    a = {i["id"] for i in client.get("/patients/p1", headers=JUDGE_A).json()["issues"]}
    b = {i["id"] for i in client.get("/patients/p1", headers=JUDGE_B).json()["issues"]}
    assert "p1:blocker:b1" in a
    assert "p1:blocker:b2" not in b


# ---------- auth + shared unit state + audit trail ----------


def signup(email="paging@example.com", name="Dr. Paging"):
    resp = client.post("/auth/register",
                       json={"email": email, "password": "nightfloat",
                             "name": name})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return {"Authorization": f"Bearer {body['token']}"}, body["doctor"]


def test_register_login_me():
    headers, doctor = signup()
    assert doctor["name"] == "Dr. Paging"
    assert client.get("/auth/me", headers=headers).json()["email"] == \
        "paging@example.com"
    resp = client.post("/auth/login", json={"email": "paging@example.com",
                                            "password": "nightfloat"})
    assert resp.status_code == 200
    assert client.post("/auth/login", json={"email": "paging@example.com",
                                            "password": "wrong"}).status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_register_validation():
    assert client.post("/auth/register", json={
        "email": "nope", "password": "nightfloat", "name": "X"}).status_code == 422
    assert client.post("/auth/register", json={
        "email": "a@b.co", "password": "shrt", "name": "X"}).status_code == 422
    signup()
    assert client.post("/auth/register", json={
        "email": "paging@example.com", "password": "nightfloat",
        "name": "Dupe"}).status_code == 409


def test_signed_in_doctors_share_unit_state():
    """Two signed-in clinicians see each other's changes (one unit state)."""
    ha, _ = signup("a@example.com", "Dr. A")
    hb, _ = signup("b@example.com", "Dr. B")
    client.patch("/issues/p1:blocker:b1", json={"action": "clear"}, headers=ha)
    b_issues = {i["id"] for i in
                client.get("/patients/p1", headers=hb).json()["issues"]}
    assert "p1:blocker:b1" not in b_issues


def test_guest_sandbox_separate_from_unit():
    ha, _ = signup()
    client.patch("/issues/p1:blocker:b1", json={"action": "clear"}, headers=JUDGE_A)
    unit = {i["id"] for i in client.get("/patients/p1", headers=ha).json()["issues"]}
    guest = {i["id"] for i in
             client.get("/patients/p1", headers=JUDGE_A).json()["issues"]}
    assert "p1:blocker:b1" in unit
    assert "p1:blocker:b1" not in guest


def test_activity_records_attribution():
    ha, doctor = signup()
    client.patch("/issues/p1:blocker:b1", json={"action": "clear"}, headers=ha)
    acts = client.get("/activity", headers=ha).json()
    assert acts and acts[0]["doctorName"] == "Dr. Paging"
    assert acts[0]["doctorId"] == doctor["id"]
    assert acts[0]["patientId"] == "p1"
    assert acts[0]["action"] == "clear"
    p1 = client.get("/activity", params={"patient": "p1"}, headers=ha).json()
    assert len(p1) == 1
    none = client.get("/activity", params={"patient": "p2"}, headers=ha).json()
    assert none == []
    mine = client.get("/activity", params={"doctor": doctor["id"]},
                      headers=ha).json()
    assert len(mine) == 1


def test_doctors_endpoint_lists_registered():
    _, d = signup()
    docs = client.get("/doctors").json()
    assert {"id": d["id"], "name": "Dr. Paging"} in docs


def test_unit_reset_records_action():
    ha, doctor = signup()
    client.patch("/issues/p1:blocker:b1", json={"action": "clear"}, headers=ha)
    client.post("/demo/reset", headers=ha)
    assert "p1:blocker:b1" in {i["id"] for i in
                             client.get("/patients/p1", headers=ha).json()["issues"]}
    acts = client.get("/activity", headers=ha).json()
    assert [a["action"] for a in acts] == ["reset"]
    assert acts[0]["doctorName"] == "Dr. Paging"
