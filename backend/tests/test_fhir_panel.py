import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import demo_patients, fhir_panel, panel

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "dataset" / "fixtures" / "p1"

NOW = datetime.now(timezone.utc)
EXPECTED_AGE = {"b1": 31, "b2": 6}  # demo values; asserted vs fixture timestamps, not hardcoded


def _load_fixtures():
    docrefs, tasks, consents, allergies = [], [], [], []
    for path in sorted(FIXTURES.glob("*.json")):
        r = json.loads(path.read_text())
        bucket = {"DocumentReference": docrefs, "Task": tasks,
                  "Consent": consents, "AllergyIntolerance": allergies}.get(r["resourceType"])
        if bucket is not None:
            bucket.append(r)
    return docrefs, tasks, consents, allergies


FAKE_PATIENT = {
    "resourceType": "Patient", "id": "42157",
    "contact": [{"name": {"text": "Daughter, on file"}}],
}


@pytest.fixture
def p1_built():
    docrefs, tasks, consents, allergies = _load_fixtures()
    overrides = {"fhirPatientId": "Patient/42157", "name": "Margaret A.", "age": 78,
                 "room": "412", "dx": "Hip fracture, ORIF post-op day 2", "dischargeInH": 30}
    return fhir_panel.build_patient_from_chart("p1", overrides, FAKE_PATIENT,
                                               docrefs, tasks, consents, allergies, NOW)


def test_build_patient_matches_demo(p1_built):
    demo = demo_patients.DEMO_PATIENTS[0]
    for key in ("name", "room", "dx", "age", "dischargeInH", "handoff"):
        assert p1_built[key] == demo[key], key
    assert p1_built["fhirPatientId"] == "Patient/42157"

    # blockers: same ids/labels/cats/waitingOn/blocks; ageH from fixture timestamps
    demo_blockers = {b["id"]: b for b in demo["blockers"]}
    assert len(p1_built["blockers"]) == len(demo_blockers)
    for b in p1_built["blockers"]:
        d = demo_blockers[b["id"]]
        for key in ("label", "cat", "waitingOn", "blocks"):
            assert b[key] == d[key]
        # compute expected ageH from the fixture authoredOn at the same `now`
        fixture_tasks = _load_fixtures()[1]
        authored = next(t["authoredOn"] for t in fixture_tasks
                        if t["id"] == f"baton-p1-blocker-{b['id']}")
        expected = round((NOW - datetime.fromisoformat(
            authored.replace("Z", "+00:00"))).total_seconds() / 3600)
        assert abs(b["ageH"] - expected) <= 1

    assert p1_built["pending"] == demo["pending"]

    # notes equal in seq order
    assert len(p1_built["notes"]) == len(demo["notes"])
    for built, demo_note in zip(p1_built["notes"], demo["notes"]):
        assert built["seq"] == demo_note["seq"]
        assert built["role"] == demo_note["role"]
        assert built["author"] == demo_note["author"]
        assert built["text"] == demo_note["text"]
        assert built["tags"] == demo_note["tags"]


def test_built_patient_issues_match_demo(p1_built):
    demo_ids = {i["id"] for i in __import__("app.rules", fromlist=["get_issues"]).get_issues(
        demo_patients.DEMO_PATIENTS[0])}
    from app.rules import get_issues
    built_ids = {i["id"] for i in get_issues(p1_built)}
    assert built_ids == demo_ids


def test_is_fixture():
    assert fhir_panel.is_fixture({"id": "x", "meta": {"tag": [
        {"system": "https://github.com/leenadudi/baton", "code": "demo-fixture"}]}})
    assert fhir_panel.is_fixture({"id": "baton-p1-note-1"})
    assert not fhir_panel.is_fixture({"id": "12345", "resourceType": "Task"})
    assert not fhir_panel.is_fixture({"id": "x", "meta": {"tag": [
        {"system": "https://github.com/leenadudi/baton", "code": "other"}]}})


@pytest.fixture
def fresh_cache(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    fhir_panel._cache.update(patients=None, loaded_at=0.0, source="demo", error=None)
    yield


class FakeFhirClient:
    """Serves fixture JSON from dataset/fixtures/<pid>/ for every persona."""

    def __init__(self, drop_docrefs_for: str | None = None):
        self.search_calls = 0
        self.drop_docrefs_for = drop_docrefs_for
        self._by_persona = {}
        fixtures_root = REPO_ROOT / "dataset" / "fixtures"
        demo_map = json.loads(
            (REPO_ROOT / "dataset" / "demo_patients.json").read_text())
        for pid, ov in demo_map.items():
            if pid.startswith("_"):
                continue
            by_type: dict[str, list] = {}
            for path in sorted((fixtures_root / pid).glob("*.json")):
                r = json.loads(path.read_text())
                by_type.setdefault(r["resourceType"], []).append(r)
            self._by_persona[ov["fhirPatientId"].split("/", 1)[1]] = (pid, by_type)

    async def get(self, resource_type, id):
        pid, _ = self._by_persona[id]
        return {"resourceType": "Patient", "id": id,
                "contact": [{"name": {"text": "Test contact"}}]}

    async def search(self, resource_type, **params):
        self.search_calls += 1
        pid, by_type = self._by_persona[params["patient"]]
        if resource_type == "DocumentReference" and pid == self.drop_docrefs_for:
            return []
        return by_type.get(resource_type, [])


def test_invalidate_throttle(fresh_cache):
    fhir_panel._cache.update(patients=[{"id": "p1"}], loaded_at=time.time(),
                             source="fhir")
    assert fhir_panel.invalidate() is False
    fhir_panel._cache["loaded_at"] = time.time() - fhir_panel.REFRESH_MIN_INTERVAL_S - 1
    assert fhir_panel.invalidate() is True
    assert fhir_panel._cache["loaded_at"] == 0.0


def test_incomplete_fixtures_raise(fresh_cache):
    fake = FakeFhirClient(drop_docrefs_for="p1")
    with pytest.raises(RuntimeError, match="incomplete fixtures for p1"):
        asyncio.run(fhir_panel.load_fhir_patients(fake))


def test_ensure_loaded_single_flight(fresh_cache, monkeypatch):
    monkeypatch.setenv("PANEL_SOURCE", "fhir")
    fake = FakeFhirClient()

    async def run_once():
        fhir_panel._cache["loaded_at"] = 0.0
        await fhir_panel.ensure_loaded(fake)
        return fake.search_calls

    baseline = asyncio.run(run_once())
    assert baseline > 0
    assert fhir_panel.status()["source"] == "fhir"

    fake.search_calls = 0
    fhir_panel._cache["loaded_at"] = 0.0
    asyncio.run(_gather5(fake))
    assert fake.search_calls == baseline


async def _gather5(fake):
    await asyncio.gather(*[fhir_panel.ensure_loaded(fake) for _ in range(5)])


def test_demo_source_returns_demo(monkeypatch):
    monkeypatch.setenv("PANEL_SOURCE", "demo")
    fhir_panel._cache.update(patients=None, loaded_at=0.0)
    asyncio.run(fhir_panel.ensure_loaded(None))
    assert fhir_panel.status()["source"] == "demo"
    patients = panel.load_patients()
    assert [p["id"] for p in patients] == [p["id"] for p in demo_patients.DEMO_PATIENTS]
