import pytest
from fastapi.testclient import TestClient

from app import fhir_write, state
from app.fhir_client import FhirClient
from app.main import app


class FakeWriter:
    base_url = "http://fake"

    def __init__(self):
        self.calls = []

    async def get(self, resource_type, id):
        return {"resourceType": resource_type, "id": id}

    async def search(self, resource_type, **params):
        self.calls.append(("search", resource_type, params))
        return []

    async def create(self, resource_type, resource):
        self.calls.append(("create", resource_type, resource))
        return {**resource, "id": "c1"}

    async def put(self, resource_type, id, resource):
        self.calls.append(("put", resource_type, id, resource))
        return {**resource, "id": id}

    async def delete(self, resource_type, id):
        self.calls.append(("delete", resource_type, id))


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PANEL_SOURCE", "demo")
    state.reset()
    yield


def test_writes_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FHIR_WRITE", raising=False)
    fake = FakeWriter()
    import asyncio
    res = asyncio.run(fhir_write.record_adopt(fake, "42157", "p1",
                                              "diet", "NPO", "text"))
    assert res is None
    assert fake.calls == []


def test_publish_brief(monkeypatch):
    monkeypatch.setenv("FHIR_WRITE", "1")
    import asyncio
    fake = FakeWriter()
    res = asyncio.run(fhir_write.publish_brief(fake, "BRIEF <text> & stuff"))
    assert res == {"id": "c1", "url": "http://fake/Composition/c1"}
    kind, rtype, comp = fake.calls[0]
    assert (kind, rtype) == ("create", "Composition")
    assert comp["status"] == "preliminary"
    codes = {t["code"] for t in comp["meta"]["tag"]}
    assert codes == {"demo-fixture", "baton-output"}
    div = comp["section"][0]["text"]["div"]
    assert "BRIEF &lt;text&gt; &amp; stuff" in div


def test_record_fill_uses_fixed_id(monkeypatch):
    monkeypatch.setenv("FHIR_WRITE", "1")
    import asyncio
    fake = FakeWriter()
    asyncio.run(fhir_write.record_fill(fake, "44086", "p2", "codeStatus", "DNR"))
    kind, rtype, rid, res = fake.calls[0]
    assert (kind, rtype, rid) == ("put", "Task", "baton-out-p2-field-codeStatus")
    assert res["description"] == "codeStatus=DNR"
    assert res["status"] == "completed"


def test_client_guards_non_output_ids():
    client = FhirClient("http://fake")
    import asyncio
    with pytest.raises(ValueError):
        asyncio.run(client.put("Task", "baton-p1-blocker-b1", {}))
    with pytest.raises(ValueError):
        asyncio.run(client.delete("Task", "123"))


def test_outputs_to_state():
    comms = [{
        "id": "c9", "sent": "2026-01-01T00:00:00+00:00",
        "topic": {"text": "weight_bearing"},
        "reasonCode": [{"text": "partial"}],
        "payload": [{"contentString": "Reconciled Weight-bearing: proceed with partial."}],
    }]
    tasks = [
        {"code": {"text": "Handoff field"}, "description": "codeStatus=Full code"},
        {"code": {"text": "Issue owner"}, "description": "p1:blocker:b1",
         "owner": {"display": "Charge RN"}},
        {"code": {"text": "Blocker cleared"}, "description": "b2"},
        {"code": {"text": "Pending owner"}, "description": "Type and screen",
         "owner": {"display": "Night Resident"}},
        {"code": {"text": "Blocker escalated"}, "description": "b1"},
    ]
    out = fhir_write.outputs_to_state("p1", comms, tasks)
    assert out["added"]["p1"][0]["tags"] == [["weight_bearing", "partial"]]
    assert out["added"]["p1"][0]["reconcile"] is True
    assert out["added"]["p1"][0]["seq"] == 501
    assert out["filled"]["p1"]["codeStatus"] == "Full code"
    assert out["owners"]["p1:blocker:b1"] == "Charge RN"
    assert out["pendOwners"]["p1|Type and screen"] == "Night Resident"
    assert out["cleared"]["p1"]["b2"] is True
    assert out["escalated"]["p1|b1"] is True

    # feed into the rule engine against a p1-shaped patient
    from app import demo_patients, rules
    p1 = next(p for p in demo_patients.DEMO_PATIENTS if p["id"] == "p1")
    issues = rules.get_issues(p1, out)
    ids = {i["id"] for i in issues}
    assert "p1:conflict:weight_bearing" not in ids
    assert "p1:blocker:b2" not in ids
    assert "p1:handoff:pend:Type and screen" not in ids
    assert "p1:conflict:anticoagulation" in ids  # untouched


def test_api_write_back(monkeypatch):
    monkeypatch.setenv("FHIR_WRITE", "1")
    fake = FakeWriter()
    monkeypatch.setattr("app.main.fhir", fake)
    client = TestClient(app)

    # create the conflict, then adopt it
    client.post("/patients/p6/notes",
                json={"role": "Surgery", "topic": "diet", "value": "NPO"})
    resp = client.patch("/issues/p6:conflict:diet",
                        json={"action": "adopt", "value": "NPO"})
    assert resp.status_code == 200
    creates = [c for c in fake.calls if c[0] == "create" and c[1] == "Communication"]
    assert len(creates) == 1
    notes = resp.json()["notes"]
    rec = next(n for n in notes if n.get("reconcile"))
    assert rec["source"] == {"resourceType": "Communication", "id": "c1"}

    pub = client.post("/brief/publish")
    assert pub.status_code == 200
    assert pub.json()["url"] == "http://fake/Composition/c1"

    reset = client.post("/demo/reset")
    assert reset.status_code == 200
    assert reset.json()["deleted"] == 0  # fake search returns no outputs
