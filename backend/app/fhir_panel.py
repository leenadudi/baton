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


def build_patient_from_chart(persona_id: str, overrides: dict, patient: dict,
                             docrefs: list, tasks: list, consents: list,
                             allergies: list, now: datetime) -> dict:
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
    return p


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
        patient, docrefs, tasks, consents, allergies, comms = await asyncio.gather(
            fhir.get("Patient", fid),
            fhir.search("DocumentReference", patient=fid, _tag=FIXTURE_TAG, _count=100),
            fhir.search("Task", patient=fid, _tag=FIXTURE_TAG, _count=100),
            fhir.search("Consent", patient=fid, _tag=FIXTURE_TAG, _count=100),
            fhir.search("AllergyIntolerance", patient=fid, _tag=FIXTURE_TAG, _count=100),
            fhir.search("Communication", patient=fid, _tag=FIXTURE_TAG, _count=100),
        )
        docrefs = [r for r in docrefs if is_fixture(r)]
        tasks = [r for r in tasks if is_fixture(r)]
        consents = [r for r in consents if is_fixture(r)]
        allergies = [r for r in allergies if is_fixture(r)]
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
                                         tasks, consents, allergies, now)
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
