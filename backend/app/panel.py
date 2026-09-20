"""Panel data assembly: demo patients + in-memory state -> API shapes (PRD 8.3)."""

import copy
import json
import time
from pathlib import Path

from app import demo_patients, fhir_panel, rules

TYPE_LABEL = {"conflict": "Conflicting instructions", "handoff": "Incomplete handoff",
              "blocker": "Administrative blocker"}

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_FHIR_FILE = REPO_ROOT / "dataset" / "demo_patients.json"


def load_patients() -> list[dict]:
    """FHIR fixtures when loaded (see fhir_panel.ensure_loaded); demo otherwise."""
    cached = fhir_panel.current_patients()
    if cached is not None:
        return cached
    patients = copy.deepcopy(demo_patients.DEMO_PATIENTS)
    fhir_ids: dict = {}
    if DEMO_FHIR_FILE.exists():
        fhir_ids = json.loads(DEMO_FHIR_FILE.read_text())
    for p in patients:
        p["fhirPatientId"] = (fhir_ids.get(p["id"]) or {}).get("fhirPatientId")
    return patients


def get_patient(pid: str) -> dict | None:
    return next((p for p in load_patients() if p["id"] == pid), None)


def build_patient(p: dict, s: dict) -> dict:
    pid = p["id"]
    filled = s["filled"].get(pid, {})
    p["handoff"] = {**p["handoff"], **filled}
    for r in p["pending"]:
        o = s["pendOwners"].get(f"{pid}|{r['name']}")
        if o is not None:
            r["owner"] = o
    p["notes"] = sorted(rules.all_notes(p, s), key=lambda n: n.get("seq", 0))
    issues = rules.get_issues(p, s)
    for i in issues:
        i["owner"] = s["owners"].get(i["id"], "")
    p["issues"] = issues
    p["risk"] = rules.risk_of(issues)
    p["dischStatus"] = rules.disch_status(p, issues)
    p["log"] = s["log"].get(pid, [])
    return p


def add_note(pid: str, note: dict, s: dict) -> None:
    note["seq"] = s["nextSeq"]
    s["nextSeq"] += 1
    note["at"] = time.time() * 1000
    note.setdefault("h", 0)
    s["added"].setdefault(pid, []).append(note)


def brief_text(s: dict) -> str:
    all_items = []
    for p in load_patients():
        for i in rules.get_issues(p, s):
            all_items.append({"p": p, "i": i})
    all_items.sort(key=lambda x: (-rules.W[x["i"]["sev"]], x["p"]["dischargeInH"]))
    un = sum(1 for x in all_items if not s["owners"].get(x["i"]["id"]))
    lines = ["SHIFT HANDOFF BRIEF for 4 West (synthetic data)",
             f"{len(all_items)} open coordination issues, {un} with no owner.", ""]
    if not all_items:
        lines.append("Nothing open. Instructions agree, handoffs are complete, no blockers.")
    for k, x in enumerate(all_items[:14]):
        i, p = x["i"], x["p"]
        lines.append(f"{k + 1}. [{i['sev'].upper()}] Rm {p['room']} {p['name']}: "
                     f"{TYPE_LABEL[i['type']]}. {i['title']}.")
        lines.append(f"   {i['sub']}")
        lines.append(f"   Owner: {s['owners'].get(i['id']) or 'UNASSIGNED'}; "
                     f"discharge target in {p['dischargeInH']}h.")
        lines.append("")
    if len(all_items) > 14:
        lines.append(f"+ {len(all_items) - 14} lower-priority items in Baton.")
    return "\n".join(lines)
