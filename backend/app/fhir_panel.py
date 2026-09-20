"""Panel data sourced from FHIR demo fixtures on the configured FHIR server.

Reads Baton-authored fixture resources (meta.tag demo-fixture / baton- ids)
for the six personas mapped in dataset/demo_patients.json and rebuilds the
exact patient dict shape the rule engine and API already consume. Demo data
remains the fallback: see ensure_loaded / PANEL_SOURCE.
"""

import asyncio
import base64
import copy
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from app import demo_patients, fhir_write, rules
from app.extract import extract
from app.fhir_client import FhirClient

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_MAP_FILE = REPO_ROOT / "dataset" / "demo_patients.json"

FIXTURE_TAG_SYSTEM = "https://github.com/leenadudi/baton"
FIXTURE_TAG_CODE = "demo-fixture"
FIXTURE_TAG = f"{FIXTURE_TAG_SYSTEM}|{FIXTURE_TAG_CODE}"
PANEL_TTL_S = 300
REFRESH_MIN_INTERVAL_S = 30

NON_BLOCKER_CODES = {"Pending result", "Follow-up owner", "Medication reconciliation"}

_cache: dict = {"patients": None, "state": None, "outputs": 0,
                "loaded_at": 0.0, "source": "demo", "error": None}
_lock = asyncio.Lock()


def is_fixture(r: dict) -> bool:
    for tag in (r.get("meta") or {}).get("tag", []):
        if tag.get("system") == FIXTURE_TAG_SYSTEM and tag.get("code") == FIXTURE_TAG_CODE:
            return True
    return str(r.get("id", "")).startswith("baton-")


# --- note tags: hand-verified ground truth as the per-note extraction cache ---

_note_tags: dict[str, list] = {}

# TODO(nicole): remove once the live FHIR fixture (dataset/fixtures/p1/
# 06-DocumentReference-baton-p1-note-6.json) is re-pushed with the reworded
# text below. Until then the public HAPI server still returns the old
# wording, which would otherwise miss the ground-truth map and drop
# Margaret's hosted SNF-vs-home conflict (the model correctly declines to
# tag a family expectation as an order).
_LEGACY_NOTE_TEXT_ALIASES = {
    "Daughter says the family expects her to come home Friday.": [["destination", "home"]],
}


def _load_ground_truth() -> None:
    if _note_tags:
        return
    for p in demo_patients.DEMO_PATIENTS:
        for n in p["notes"]:
            _note_tags[n["text"].strip()] = [list(t) for t in n["tags"]]
    for text, tags in _LEGACY_NOTE_TEXT_ALIASES.items():
        _note_tags.setdefault(text, [list(t) for t in tags])


def tags_lookup(text: str) -> list:
    """Sync lookup used by build_patient_from_chart."""
    _load_ground_truth()
    return copy.deepcopy(_note_tags.get(text.strip(), []))


async def tags_for(text: str, role: str | None = None) -> list:
    """Ground truth first; else OpenAI extraction; else no tags."""
    known = tags_lookup(text)
    if known:
        return known
    if os.environ.get("OPENAI_API_KEY"):
        result = await extract(text, role)
        tags = [[t["topic"], t["value"]] for t in result["tags"]]
        _note_tags[text.strip()] = tags
        return tags
    return []


def _hours_since(ts: str | None, now: datetime) -> int:
    if not ts:
        return 0
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return round((now - dt).total_seconds() / 3600)


def _decode_docref_text(dr: dict) -> str:
    for c in dr.get("content", []):
        data = (c.get("attachment") or {}).get("data")
        if data:
            return base64.b64decode(data).decode("utf-8")
    return ""


def _coding_text(concept: dict | None) -> str:
    if not concept:
        return ""
    if concept.get("text"):
        return concept["text"]
    return (concept.get("coding") or [{}])[0].get("display", "")


OBS_CATEGORIES = ("laboratory", "social-history", "vital-signs")


def _obs_category(obs: dict) -> str | None:
    for cat in obs.get("category", []):
        for coding in cat.get("coding", []):
            if coding.get("code") in OBS_CATEGORIES:
                return coding["code"]
    return None


def _obs_value(obs: dict) -> str:
    if "valueQuantity" in obs:
        vq = obs["valueQuantity"]
        return f"{vq.get('value', '')} {vq.get('unit', '')}".strip()
    if "valueCodeableConcept" in obs:
        return _coding_text(obs["valueCodeableConcept"])
    if "valueString" in obs:
        return obs["valueString"]
    # Multi-component vitals (e.g. blood pressure: separate systolic/diastolic
    # components, no top-level value) — join each component's own value.
    if obs.get("component"):
        parts = []
        for c in obs["component"]:
            vq = c.get("valueQuantity") or {}
            if vq.get("value") is not None:
                parts.append(f"{_coding_text(c.get('code'))}: {vq['value']} {vq.get('unit', '')}".strip())
        return "; ".join(parts)
    return ""


def _obs_date(obs: dict) -> str | None:
    return obs.get("effectiveDateTime") or obs.get("issued")


PERIOD_UNIT_WORDS = {"d": "day", "h": "hr", "wk": "week", "mo": "month"}


def _dosage_text(m: dict) -> str:
    """Prefer dosageInstruction.text; Synthea usually omits it, so fall back
    to formatting the structured doseAndRate/timing fields it does provide."""
    dosage = (m.get("dosageInstruction") or [{}])[0]
    if dosage.get("text"):
        return dosage["text"]
    bits = []
    for dr in dosage.get("doseAndRate", []):
        q = dr.get("doseQuantity") or {}
        if q.get("value") is not None and q.get("unit"):
            bits.append(f"{q['value']} {q['unit']}")
    repeat = (dosage.get("timing") or {}).get("repeat") or {}
    freq, period, unit = repeat.get("frequency"), repeat.get("period"), repeat.get("periodUnit")
    if freq and period and unit:
        unit_word = PERIOD_UNIT_WORDS.get(unit, unit)
        bits.append(f"{freq}x/{unit_word}" if period == 1 else f"{freq}x/{period:g}{unit_word}")
    return ", ".join(bits)


def _med_summary(m: dict) -> dict:
    return {
        "name": _coding_text(m.get("medicationCodeableConcept")),
        "dose": _dosage_text(m),
        "date": m.get("authoredOn"),
    }


def _condition_summary(c: dict) -> dict:
    return {"name": _coding_text(c.get("code")), "onset": c.get("onsetDateTime")}


def _procedure_summary(p: dict) -> dict:
    return {
        "name": _coding_text(p.get("code")),
        "date": p.get("performedDateTime") or (p.get("performedPeriod") or {}).get("start"),
    }


def _careteam_roster(care_teams: list) -> list:
    seen: set[str] = set()
    roster = []
    for ct in care_teams:
        for part in ct.get("participant", []):
            name = (part.get("member") or {}).get("display")
            if not name or name in seen:
                continue
            seen.add(name)
            roster.append({"name": name, "role": _coding_text((part.get("role") or [{}])[0])})
    return roster


RECENT_ENCOUNTERS_LIMIT = 20
RECENT_PROCEDURES_LIMIT = 15


def _build_patient_info(patient: dict, observations: list, encounters: list,
                        medications: list | None = None, conditions: list | None = None,
                        procedures: list | None = None, care_teams: list | None = None) -> dict:
    """Reference data pulled straight from the chart so a clinician doesn't
    need a second system open: DOB/sex, latest-per-test labs and vitals,
    latest-per-fact social history (smoking, alcohol, drug use), recent
    encounters/procedures, active medications and problems, and the care
    team roster.

    Labs/vitals/social-history/encounters/procedures aren't Baton fixtures —
    they're read from every Observation/Encounter/Procedure on the patient,
    not just baton-tagged ones — and are best-effort (see
    _fetch_info_resources). Medications/conditions are filtered server-side
    to active only. The care team roster IS a Baton fixture (Amy's
    load_fixtures.py generates one CareTeam per persona from the same
    role/author pairs already on the notes), fetched with the other fixture
    resources in load_fhir_patients.

    Synthea re-records unchanged social-history facts (e.g. "Ex-smoker") at
    every checkup for decades, and Encounter/Procedure history can span a
    lifetime — both are deduped/capped here since FhirClient.search()'s
    _count only bounds page size, not the total paginated result."""
    labs: list[dict] = []
    vitals: list[dict] = []
    social: list[dict] = []
    seen_labs: set[str] = set()
    seen_vitals: set[str] = set()
    seen_social: set[str] = set()
    # observations arrive newest-first (_sort=-date), so first occurrence per
    # test/fact name is the latest result.
    for obs in observations:
        name = _coding_text(obs.get("code"))
        if not name:
            continue
        category = _obs_category(obs)
        entry = {"name": name, "value": _obs_value(obs), "date": _obs_date(obs)}
        if category == "laboratory" and name not in seen_labs:
            seen_labs.add(name)
            labs.append(entry)
        elif category == "vital-signs" and name not in seen_vitals:
            seen_vitals.add(name)
            vitals.append(entry)
        elif category == "social-history" and name not in seen_social:
            seen_social.add(name)
            social.append(entry)

    visits = []
    for enc in encounters[:RECENT_ENCOUNTERS_LIMIT]:
        period = enc.get("period") or {}
        visits.append({
            "date": period.get("start"),
            "type": _coding_text((enc.get("type") or [{}])[0]),
            "reason": _coding_text((enc.get("reasonCode") or [{}])[0]),
            "status": enc.get("status"),
        })

    return {
        "dob": patient.get("birthDate"),
        "gender": patient.get("gender"),
        "labs": labs,
        "vitals": vitals,
        "socialHistory": social,
        "encounters": visits,
        "medications": [_med_summary(m) for m in (medications or [])],
        "conditions": [_condition_summary(c) for c in (conditions or [])],
        "procedures": [_procedure_summary(p) for p in (procedures or [])[:RECENT_PROCEDURES_LIMIT]],
        "careTeam": _careteam_roster(care_teams or []),
    }


def build_patient_from_chart(persona_id: str, overrides: dict, patient: dict,
                             docrefs: list, tasks: list, consents: list,
                             allergies: list, now: datetime,
                             observations: list | None = None,
                             encounters: list | None = None,
                             medications: list | None = None,
                             conditions: list | None = None,
                             procedures: list | None = None,
                             care_teams: list | None = None) -> dict:
    demo = next((p for p in demo_patients.DEMO_PATIENTS if p["id"] == persona_id), {})

    p = {
        "id": persona_id,
        "name": overrides.get("name") or demo.get("name"),
        "age": overrides.get("age") if overrides.get("age") is not None else demo.get("age"),
        "room": overrides.get("room") or demo.get("room"),
        "dx": overrides.get("dx") or demo.get("dx"),
        "dischargeInH": overrides.get("dischargeInH")
                        if overrides.get("dischargeInH") is not None
                        else demo.get("dischargeInH"),
        "fhirPatientId": overrides.get("fhirPatientId"),
    }

    notes = []
    for dr in docrefs:
        notes.append({
            "role": (dr.get("category") or [{}])[0].get("text"),
            "author": (dr.get("author") or [{}])[0].get("display"),
            "h": _hours_since(dr.get("date"), now),
            "text": _decode_docref_text(dr),
            "tags": tags_lookup(_decode_docref_text(dr)),
            "source": {"resourceType": "DocumentReference", "id": dr.get("id")},
        })
    rules.assign_seq(notes)
    p["notes"] = notes

    open_tasks = [t for t in tasks if t.get("status") != "completed"]
    prefix = f"baton-{persona_id}-blocker-"
    p["blockers"] = [
        {"id": t["id"][len(prefix):] if str(t.get("id", "")).startswith(prefix) else t.get("id"),
         "label": t.get("description"),
         "cat": (t.get("code") or {}).get("text"),
         "waitingOn": (t.get("owner") or {}).get("display") or "",
         "ageH": _hours_since(t.get("authoredOn"), now),
         "blocks": t.get("priority") == "urgent",
         "source": {"resourceType": "Task", "id": t.get("id")}}
        for t in open_tasks
        if (t.get("code") or {}).get("text") not in NON_BLOCKER_CODES
    ]
    p["pending"] = [
        {"name": t.get("description"),
         "owner": (t.get("owner") or {}).get("display") or "",
         "source": {"resourceType": "Task", "id": t.get("id")}}
        for t in open_tasks
        if (t.get("code") or {}).get("text") == "Pending result"
    ]

    code_status = ""
    for c in consents:
        code = ((c.get("provision") or {}).get("code") or [{}])[0]
        if code.get("text"):
            code_status = code["text"]
            break
    allergy_texts = []
    for a in allergies:
        text = (a.get("code") or {}).get("text") or ""
        allergy_texts.append("NKDA" if text == "No known drug allergies" else text)
    follow_up = next((t for t in tasks
                      if (t.get("code") or {}).get("text") == "Follow-up owner"), None)
    med_rec = next((t for t in tasks
                    if (t.get("code") or {}).get("text") == "Medication reconciliation"), None)
    contact = (patient.get("contact") or [{}])[0]
    p["handoff"] = {
        "codeStatus": code_status,
        "allergies": "; ".join(allergy_texts),
        "familyContact": (contact.get("name") or {}).get("text", ""),
        "followUpOwner": ((follow_up.get("owner") or {}).get("display")
                          or follow_up.get("description") or "") if follow_up else "",
        "medRec": (med_rec.get("description") or "") if med_rec else "",
    }
    p["info"] = _build_patient_info(patient, observations or [], encounters or [],
                                    medications, conditions, procedures, care_teams)
    return p


async def _fetch_info_resources(fhir: FhirClient, fid: str) -> tuple[list, list, list, list, list]:
    """Observation/Encounter/MedicationRequest/Condition/Procedure for the
    patient-info panel. Reference-only data — a flaky call here must not fail
    the whole panel load the way a missing fixture resource does, so it
    degrades to an empty info section instead."""
    try:
        return await asyncio.gather(
            fhir.search("Observation", patient=fid,
                       category="laboratory,social-history,vital-signs",
                       _sort="-date", _count=200),
            fhir.search("Encounter", patient=fid, _sort="-date", _count=20),
            fhir.search("MedicationRequest", patient=fid, status="active", _count=50),
            fhir.search("Condition", patient=fid, **{"clinical-status": "active"}, _count=50),
            fhir.search("Procedure", patient=fid, _sort="-date", _count=50),
        )
    except Exception:
        log.warning("Failed to fetch patient-info resources for %s", fid, exc_info=True)
        return [], [], [], [], []


async def load_fhir_patients(fhir: FhirClient) -> tuple[list[dict], dict, int]:
    """Fetch fixture resources for each mapped persona and rebuild panel patients.

    Returns (patients, chart_state, n_outputs): chart_state merges Baton's own
    baton-out-* write-back resources into a state.fresh()-shaped dict.
    """
    demo_map = json.loads(DEMO_MAP_FILE.read_text())
    personas = {k: v for k, v in demo_map.items() if not k.startswith("_")}
    now = datetime.now(timezone.utc)
    out = []
    chart_state = {"added": {}, "filled": {}, "cleared": {}, "escalated": {},
                   "pendOwners": {}, "owners": {}}
    n_outputs = 0
    for pid, overrides in personas.items():
        ref = (overrides.get("fhirPatientId") or "")
        if not ref.startswith("Patient/"):
            continue
        fid = ref.split("/", 1)[1]
        patient, docrefs, tasks, consents, allergies, comms, care_teams = await asyncio.gather(
            fhir.get("Patient", fid),
            fhir.search("DocumentReference", patient=fid, _tag=FIXTURE_TAG, _count=100),
            fhir.search("Task", patient=fid, _tag=FIXTURE_TAG, _count=100),
            fhir.search("Consent", patient=fid, _tag=FIXTURE_TAG, _count=100),
            fhir.search("AllergyIntolerance", patient=fid, _tag=FIXTURE_TAG, _count=100),
            fhir.search("Communication", patient=fid, _tag=FIXTURE_TAG, _count=100),
            fhir.search("CareTeam", patient=fid, _tag=FIXTURE_TAG, _count=20),
        )
        observations, encounters, medications, conditions, procedures = await _fetch_info_resources(fhir, fid)
        docrefs = [r for r in docrefs if is_fixture(r)]
        tasks = [r for r in tasks if is_fixture(r)]
        consents = [r for r in consents if is_fixture(r)]
        allergies = [r for r in allergies if is_fixture(r)]
        care_teams = [r for r in care_teams if is_fixture(r)]
        output_comms = [r for r in comms if fhir_write.is_output(r)]
        output_tasks = [t for t in tasks if fhir_write.is_output(t)]
        tasks = [t for t in tasks if not fhir_write.is_output(t)]
        n_outputs += len(output_comms) + len(output_tasks)
        pstate = fhir_write.outputs_to_state(pid, output_comms, output_tasks)
        for k, v in pstate.items():
            if isinstance(v, dict):
                chart_state[k].update(v)
        # pre-resolve any note text missing from the ground-truth map
        await asyncio.gather(*(
            tags_for(_decode_docref_text(dr),
                     (dr.get("category") or [{}])[0].get("text"))
            for dr in docrefs
        ))
        demo = next(p for p in demo_patients.DEMO_PATIENTS if p["id"] == pid)
        built = build_patient_from_chart(pid, overrides, patient, docrefs,
                                         tasks, consents, allergies, now,
                                         observations, encounters,
                                         medications, conditions, procedures, care_teams)
        missing = []
        if len(built["notes"]) < len(demo["notes"]):
            missing.append(f"notes {len(built['notes'])}/{len(demo['notes'])}")
        if len(built["blockers"]) < len(demo["blockers"]):
            missing.append(f"blockers {len(built['blockers'])}/{len(demo['blockers'])}")
        if len(built["pending"]) < len(demo["pending"]):
            missing.append(f"pending {len(built['pending'])}/{len(demo['pending'])}")
        for key, expected in demo["handoff"].items():
            if expected and not built["handoff"].get(key):
                missing.append(f"handoff.{key}")
        if missing:
            raise RuntimeError(
                f"incomplete fixtures for {pid}: missing {', '.join(missing)}")
        out.append(built)
    return out, chart_state, n_outputs


async def ensure_loaded(fhir: FhirClient) -> None:
    source = os.environ.get("PANEL_SOURCE", "fhir")
    if source == "demo":
        _cache.update(patients=None, source="demo", error=None,
                      loaded_at=time.time())
        return
    if time.time() - _cache["loaded_at"] < PANEL_TTL_S:
        return
    async with _lock:
        # another request may have populated the cache while we waited
        if time.time() - _cache["loaded_at"] < PANEL_TTL_S:
            return
        try:
            patients, cstate, n_out = await load_fhir_patients(fhir)
            _cache.update(patients=patients, state=cstate, outputs=n_out,
                          source="fhir", error=None, loaded_at=time.time())
        except Exception as exc:
            log.warning("FHIR panel load failed, falling back to demo data: %s", exc)
            _cache.update(patients=None, state=None, outputs=0, source="demo",
                          error=str(exc), loaded_at=time.time())


def invalidate() -> bool:
    """Force the next ensure_loaded to reload. Rate-limited: returns False if
    a fhir load happened less than REFRESH_MIN_INTERVAL_S ago."""
    if (_cache["source"] == "fhir"
            and time.time() - _cache["loaded_at"] < REFRESH_MIN_INTERVAL_S):
        return False
    _cache["loaded_at"] = 0.0
    return True


def force_invalidate() -> None:
    _cache["loaded_at"] = 0.0


def chart_state() -> dict | None:
    if _cache["state"] is None:
        return None
    return copy.deepcopy(_cache["state"])


def current_patients() -> list[dict] | None:
    if _cache["patients"] is None:
        return None
    return copy.deepcopy(_cache["patients"])


def status() -> dict:
    return {"source": _cache["source"], "loaded_at": _cache["loaded_at"],
            "error": _cache["error"], "ttl_s": PANEL_TTL_S,
            "fhir_write": fhir_write.enabled(), "outputs": _cache["outputs"]}
