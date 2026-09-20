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

    pending = [{k: v for k, v in p.items() if k != "source"}
               for p in p1_built["pending"]]
    assert pending == demo["pending"]
    assert all(p["source"]["resourceType"] == "Task" for p in p1_built["pending"])

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

    def __init__(self, drop_docrefs_for: str | None = None,
                 drop: dict[str, set] | None = None,
                 extra: dict[str, dict] | None = None):
        self.search_calls = 0
        self.drop_docrefs_for = drop_docrefs_for
        self.drop = drop or {}
        self.extra = extra or {}
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
        if resource_type in self.drop.get(pid, set()):
            return []
        return by_type.get(resource_type, []) + self.extra.get(pid, {}).get(resource_type, [])


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


def test_incomplete_fixtures_handoff(fresh_cache):
    fake = FakeFhirClient(drop={"p1": {"Consent"}})
    with pytest.raises(RuntimeError, match="incomplete fixtures for p1: missing handoff.codeStatus"):
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


OUT_META = {"tag": [{"system": "https://github.com/leenadudi/baton", "code": "demo-fixture"},
                    {"system": "https://github.com/leenadudi/baton", "code": "baton-output"}]}


def test_outputs_read_back(fresh_cache, monkeypatch):
    """Baton's own baton-out-* writes are folded back into effective state."""
    monkeypatch.setenv("PANEL_SOURCE", "fhir")
    comm = {"resourceType": "Communication", "id": "baton-out-comm-1",
            "sent": "2026-01-01T00:00:00+00:00", "topic": {"text": "weight_bearing"},
            "reasonCode": [{"text": "partial"}],
            "payload": [{"contentString": "Reconciled Weight-bearing: proceed with partial."}],
            "meta": OUT_META}
    field_task = {"resourceType": "Task", "id": "baton-out-p2-field-codeStatus",
                  "status": "completed", "intent": "order",
                  "code": {"text": "Handoff field"}, "description": "codeStatus=Full code",
                  "authoredOn": "2026-01-01T00:00:00+00:00", "meta": OUT_META}
    fake = FakeFhirClient(extra={"p1": {"Communication": [comm]},
                                 "p2": {"Task": [field_task]}})
    asyncio.run(fhir_panel.ensure_loaded(fake))
    assert fhir_panel.status()["outputs"] == 2

    from app import state
    state.reset()
    p1 = panel.build_patient(panel.get_patient("p1"))
    assert "p1:conflict:weight_bearing" not in {i["id"] for i in p1["issues"]}
    p2 = panel.build_patient(panel.get_patient("p2"))
    assert p2["handoff"]["codeStatus"] == "Full code"
    assert "p2:handoff:codeStatus" not in {i["id"] for i in p2["issues"]}


def test_demo_source_returns_demo(monkeypatch):
    monkeypatch.setenv("PANEL_SOURCE", "demo")
    fhir_panel._cache.update(patients=None, loaded_at=0.0)
    asyncio.run(fhir_panel.ensure_loaded(None))
    assert fhir_panel.status()["source"] == "demo"
    patients = panel.load_patients()
    assert [p["id"] for p in patients] == [p["id"] for p in demo_patients.DEMO_PATIENTS]


def _obs(category, name, value=None, date="2026-01-01T00:00:00Z"):
    entry = {"category": [{"coding": [{"code": category}]}],
             "code": {"text": name}, "effectiveDateTime": date}
    if value is not None:
        entry["valueQuantity"] = {"value": value, "unit": "mg/dL"}
    return entry


def test_build_patient_info_dedupes_and_caps():
    # newest-first input, as _sort=-date returns; older duplicate entries for
    # the same lab/social-history fact must be dropped, keeping only the latest.
    observations = [
        _obs("laboratory", "Hemoglobin", 9.6, "2026-09-18T10:00:00Z"),
        _obs("laboratory", "Hemoglobin", 12.1, "2026-08-01T10:00:00Z"),  # older dup, dropped
        _obs("laboratory", "Potassium", 4.2, "2026-09-18T10:00:00Z"),
        _obs("social-history", "Tobacco smoking status", None, "2020-01-01T00:00:00Z"),
        _obs("social-history", "Tobacco smoking status", None, "2015-01-01T00:00:00Z"),  # older dup
    ]
    observations[3]["valueCodeableConcept"] = {"text": "Former smoker"}
    observations[4]["valueCodeableConcept"] = {"text": "Former smoker"}
    encounters = [
        {"period": {"start": f"202{n}-01-01T00:00:00Z"}, "status": "finished"}
        for n in range(9, -1, -1)  # 10 encounters this decade
    ] + [
        {"period": {"start": f"19{90 + n}-01-01T00:00:00Z"}, "status": "finished"}
        for n in range(15)  # 15 more from the 90s -> 25 total, over the cap of 20
    ]

    info = fhir_panel._build_patient_info(
        {"birthDate": "1948-03-12", "gender": "female"}, observations, encounters)

    assert info["dob"] == "1948-03-12"
    assert [l["name"] for l in info["labs"]] == ["Hemoglobin", "Potassium"]
    assert info["labs"][0]["value"] == "9.6 mg/dL"  # kept the newer of the two Hemoglobin reads
    assert len(info["socialHistory"]) == 1
    assert info["socialHistory"][0]["date"] == "2020-01-01T00:00:00Z"
    assert len(info["encounters"]) == fhir_panel.RECENT_ENCOUNTERS_LIMIT


def test_build_patient_matches_demo_has_info(p1_built):
    # build_patient_from_chart defaults every info source to [] when the
    # caller (e.g. this test's fixture) doesn't pass any.
    assert p1_built["info"] == {"dob": None, "gender": None, "labs": [], "vitals": [],
                                "socialHistory": [], "encounters": [], "medications": [],
                                "conditions": [], "procedures": [], "careTeam": []}


def test_panel_build_patient_defaults_info_for_demo_fallback():
    demo_p1 = next(p for p in demo_patients.DEMO_PATIENTS if p["id"] == "p1")
    built = panel.build_patient(json.loads(json.dumps(demo_p1)))
    assert built["info"] is None


def test_build_patient_info_vitals_medications_conditions_procedures_careteam():
    observations = [
        _obs("vital-signs", "Heart rate", 72, "2026-09-19T00:00:00Z"),
        _obs("vital-signs", "Heart rate", 68, "2026-09-18T00:00:00Z"),  # older dup, dropped
    ]
    bp = {
        "category": [{"coding": [{"code": "vital-signs"}]}],
        "code": {"text": "Blood pressure panel"},
        "effectiveDateTime": "2026-09-19T00:00:00Z",
        "component": [
            {"code": {"text": "Systolic"}, "valueQuantity": {"value": 128, "unit": "mm[Hg]"}},
            {"code": {"text": "Diastolic"}, "valueQuantity": {"value": 82, "unit": "mm[Hg]"}},
        ],
    }
    observations.append(bp)
    medications = [{"medicationCodeableConcept": {"text": "Lisinopril 10 MG"},
                    "dosageInstruction": [{"text": "1 tablet daily"}],
                    "authoredOn": "2026-09-01T00:00:00Z"}]
    conditions = [{"code": {"text": "Type 2 diabetes"}, "onsetDateTime": "2018-01-01T00:00:00Z"}]
    procedures = [{"code": {"text": "ORIF hip"}, "performedDateTime": "2026-09-17T00:00:00Z"}]
    care_teams = [{"participant": [
        {"role": [{"text": "Orthopedics"}], "member": {"display": "Dr. Reyes"}},
        {"role": [{"text": "Hospitalist"}], "member": {"display": "Dr. Okafor"}},
    ]}]

    info = fhir_panel._build_patient_info(
        {"birthDate": "1948-03-12", "gender": "female"}, observations, [],
        medications, conditions, procedures, care_teams)

    assert [v["name"] for v in info["vitals"]] == ["Heart rate", "Blood pressure panel"]
    assert info["vitals"][0]["value"] == "72 mg/dL"
    assert info["vitals"][1]["value"] == "Systolic: 128 mm[Hg]; Diastolic: 82 mm[Hg]"
    assert info["medications"] == [{"name": "Lisinopril 10 MG", "dose": "1 tablet daily",
                                    "date": "2026-09-01T00:00:00Z"}]
    assert info["conditions"] == [{"name": "Type 2 diabetes", "onset": "2018-01-01T00:00:00Z"}]
    assert info["procedures"] == [{"name": "ORIF hip", "date": "2026-09-17T00:00:00Z"}]
    assert info["careTeam"] == [{"name": "Dr. Reyes", "role": "Orthopedics"},
                                {"name": "Dr. Okafor", "role": "Hospitalist"}]


def test_dosage_text_falls_back_to_structured_fields():
    # Synthea usually omits dosageInstruction.text entirely, leaving only
    # timing.repeat / doseAndRate — this is the shape #35's dose came back
    # blank against on the live server.
    no_dosage = {"medicationCodeableConcept": {"text": "Alteplase 100 MG Injection"}}
    assert fhir_panel._dosage_text(no_dosage) == ""

    structured = {"dosageInstruction": [{
        "timing": {"repeat": {"frequency": 1, "period": 1.0, "periodUnit": "d"}},
        "doseAndRate": [{"doseQuantity": {"value": 1.0}}],
    }]}
    assert fhir_panel._dosage_text(structured) == "1x/day"

    with_unit_and_freq = {"dosageInstruction": [{
        "timing": {"repeat": {"frequency": 2, "period": 1.0, "periodUnit": "d"}},
        "doseAndRate": [{"doseQuantity": {"value": 500, "unit": "mg"}}],
    }]}
    assert fhir_panel._dosage_text(with_unit_and_freq) == "500 mg, 2x/day"

    has_text = {"dosageInstruction": [{"text": "1 tablet by mouth daily"}]}
    assert fhir_panel._dosage_text(has_text) == "1 tablet by mouth daily"


def test_build_patient_info_procedures_capped():
    procedures = [{"code": {"text": f"Procedure {i}"}, "performedDateTime": "2026-01-01T00:00:00Z"}
                 for i in range(30)]
    info = fhir_panel._build_patient_info({}, [], [], procedures=procedures)
    assert len(info["procedures"]) == fhir_panel.RECENT_PROCEDURES_LIMIT


def test_careteam_fetched_and_filtered_by_fixture_tag(fresh_cache, monkeypatch):
    monkeypatch.setenv("PANEL_SOURCE", "fhir")
    fake = FakeFhirClient()
    patients, _, _ = asyncio.run(fhir_panel.load_fhir_patients(fake))
    p1 = next(p for p in patients if p["id"] == "p1")
    names = {m["name"] for m in p1["info"]["careTeam"]}
    assert "Dr. Reyes" in names
    assert "Dr. Okafor" in names
