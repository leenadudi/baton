import asyncio
import json
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


def test_demo_source_returns_demo(monkeypatch):
    monkeypatch.setenv("PANEL_SOURCE", "demo")
    fhir_panel._cache.update(patients=None, loaded_at=0.0)
    asyncio.run(fhir_panel.ensure_loaded(None))
    assert fhir_panel.status()["source"] == "demo"
    patients = panel.load_patients()
    assert [p["id"] for p in patients] == [p["id"] for p in demo_patients.DEMO_PATIENTS]
