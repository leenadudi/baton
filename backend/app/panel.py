"""Panel data assembly: demo patients + in-memory state -> API shapes (PRD 8.3)."""

import copy
import json
import time
from pathlib import Path

from app import demo_patients, fhir_panel, rules, state
from app.state import STATE, log_act

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


def effective_state() -> dict:
    """Chart write-back state (fhir_panel.chart_state) overlaid with the
    in-memory STATE; in-memory wins on conflicts."""
    eff = state.fresh()
    chart = fhir_panel.chart_state() or {}
    for key, val in chart.items():
        if isinstance(val, dict):
            eff[key].update(copy.deepcopy(val))
    for key in ("filled", "cleared"):  # per-pid dict-of-dicts
        for pid, sub in STATE[key].items():
            eff[key].setdefault(pid, {}).update(sub)
    for key in ("escalated", "pendOwners", "owners"):
        eff[key].update(STATE[key])
    chart_notes = eff["added"]
    for pid, notes in STATE["added"].items():
        known = {((n.get("source") or {}).get("id")) for n in chart_notes.get(pid, [])}
        extra = [n for n in notes if (n.get("source") or {}).get("id") not in known]
        eff["added"].setdefault(pid, []).extend(extra)
    eff["log"] = STATE["log"]
    eff["nextSeq"] = STATE["nextSeq"]
    return eff


def get_patient(pid: str) -> dict | None:
    return next((p for p in load_patients() if p["id"] == pid), None)


def build_patient(p: dict) -> dict:
    pid = p["id"]
    S = effective_state()
    filled = S["filled"].get(pid, {})
    p["handoff"] = {**p["handoff"], **filled}
    for r in p["pending"]:
        o = S["pendOwners"].get(f"{pid}|{r['name']}")
        if o is not None:
            r["owner"] = o
    p["notes"] = sorted(rules.all_notes(p, S), key=lambda n: n.get("seq", 0))
    issues = rules.get_issues(p, S)
    for i in issues:
        i["owner"] = S["owners"].get(i["id"], "")
    p["issues"] = issues
    p["risk"] = rules.risk_of(issues)
    p["dischStatus"] = rules.disch_status(p, issues)
    p["log"] = S["log"].get(pid, [])
    return p


def add_note(pid: str, note: dict) -> None:
    note["seq"] = STATE["nextSeq"]
    STATE["nextSeq"] += 1
    note["at"] = time.time() * 1000
    note.setdefault("h", 0)
    STATE["added"].setdefault(pid, []).append(note)


def brief_text() -> str:
    S = effective_state()
    all_items = []
    for p in load_patients():
        for i in rules.get_issues(p, S):
            all_items.append({"p": p, "i": i})
    all_items.sort(key=lambda x: (-rules.W[x["i"]["sev"]], x["p"]["dischargeInH"]))
    un = sum(1 for x in all_items if not S["owners"].get(x["i"]["id"]))
    lines = ["SHIFT HANDOFF BRIEF for 4 West (synthetic data)",
             f"{len(all_items)} open coordination issues, {un} with no owner.", ""]
    if not all_items:
        lines.append("Nothing open. Instructions agree, handoffs are complete, no blockers.")
    for k, x in enumerate(all_items[:14]):
        i, p = x["i"], x["p"]
        lines.append(f"{k + 1}. [{i['sev'].upper()}] Rm {p['room']} {p['name']}: "
                     f"{TYPE_LABEL[i['type']]}. {i['title']}.")
        lines.append(f"   {i['sub']}")
        lines.append(f"   Owner: {S['owners'].get(i['id']) or 'UNASSIGNED'}; "
                     f"discharge target in {p['dischargeInH']}h.")
        lines.append("")
    if len(all_items) > 14:
        lines.append(f"+ {len(all_items) - 14} lower-priority items in Baton.")
    return "\n".join(lines)
