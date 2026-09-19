"""Rule engine ported from frontend/public/prototype.html (lines 269-429).

Data model: patient dict with keys id, name, dischargeInH, handoff{...},
pending[{name, owner}], blockers[{id, label, cat, waitingOn, ageH, blocks}],
notes[{role, author, h, text, tags: [[topic, value], ...], reconcile?, seq?}].

`state` mirrors the prototype's persisted dicts:
    filled:      {pid: {fieldKey: value}}
    pendOwners:  {"pid|result name": owner}
    cleared:     {pid: {blockerId: true}}
    escalated:   {"pid|blockerId": true}
    added:       {pid: [notes appended after load]}
"""

TOPICS = {
    "anticoagulation": {"label": "Anticoagulation", "values": ["continue", "hold"], "sev": "high"},
    "weight_bearing": {"label": "Weight-bearing", "values": ["full", "partial", "non-weight-bearing"], "sev": "high"},
    "destination": {"label": "Discharge destination", "values": ["home", "home with home health", "SNF", "inpatient rehab"], "sev": "high"},
    "diet": {"label": "Diet", "values": ["regular", "cardiac 2g Na", "carb-consistent", "NPO", "clear liquids"], "sev": "med"},
    "fluids": {"label": "Fluids", "values": ["restrict", "encourage"], "sev": "med"},
    "isolation": {"label": "Isolation", "values": ["contact precautions", "none"], "sev": "med"},
}

FIELDS = [
    {"key": "codeStatus", "label": "Code status", "sev": "high",
     "why": "Oncoming staff cannot act safely in an emergency without it.",
     "ph": "e.g. Full code"},
    {"key": "allergies", "label": "Allergies", "sev": "high",
     "why": "Allergy status is not documented in the handoff, so orders may be placed without it.",
     "ph": "e.g. NKDA, or drug and reaction"},
    {"key": "followUpOwner", "label": "Post-discharge follow-up owner", "sev": "med",
     "why": "Nobody is named to see this patient after discharge, so follow-up is likely to slip.",
     "ph": "e.g. PCP Dr. Hale"},
    {"key": "medRec", "label": "Medication reconciliation", "sev": "med",
     "why": "Discharge medications have not been reconciled against home medications.",
     "ph": "e.g. Done by pharmacy"},
    {"key": "familyContact", "label": "Family or surrogate contact", "sev": "low",
     "why": "No one is listed to call if the patient's status changes or a plan needs consent.",
     "ph": "e.g. Daughter, on file"},
]

W = {"high": 3, "med": 2, "low": 1}


def empty_state() -> dict:
    return {"added": {}, "filled": {}, "pendOwners": {}, "cleared": {}, "escalated": {}}


def assign_seq(notes: list[dict]) -> list[dict]:
    """Sort notes newest-first (h desc) and assign seq = 1..n, as the prototype does."""
    notes.sort(key=lambda n: -n["h"])
    for i, n in enumerate(notes):
        n["seq"] = i + 1
    return notes


def all_notes(p: dict, state: dict) -> list[dict]:
    return list(p["notes"]) + state.get("added", {}).get(p["id"], [])


def tag_of(note: dict, topic: str):
    for t in note.get("tags", []):
        if t[0] == topic:
            return t[1]
    return None


def find_conflicts(p: dict, state: dict | None = None) -> list[dict]:
    state = state or empty_state()
    notes = all_notes(p, state)
    out = []
    for topic in TOPICS:
        tn = [n for n in notes if tag_of(n, topic) is not None]
        if not tn:
            continue
        barrier = max((n["seq"] for n in tn if n.get("reconcile")), default=0)
        latest: dict[str, dict] = {}
        for n in tn:
            if n["seq"] >= barrier and (n["role"] not in latest or n["seq"] > latest[n["role"]]["seq"]):
                latest[n["role"]] = n
        vals: dict[str, list[dict]] = {}
        for n in latest.values():
            vals.setdefault(tag_of(n, topic), []).append(n)
        if len(vals) > 1:
            out.append({"topic": topic, "vals": vals})
    return out


def get_issues(p: dict, state: dict | None = None) -> list[dict]:
    S = state or empty_state()
    issues = []
    for c in find_conflicts(p, S):
        T = TOPICS[c["topic"]]
        vs = list(c["vals"].keys())
        sub = [f"{n['role']}: {v}" for v in vs for n in c["vals"][v]]
        issues.append({
            "id": f"{p['id']}:conflict:{c['topic']}", "pid": p["id"], "type": "conflict",
            "sev": T["sev"],
            "title": f"{T['label']}: {len(vs)} different instructions are active",
            "sub": "; ".join(sub),
            "why": "Both cannot be followed. Until someone picks one, whoever reads the chart next may follow either.",
            "topic": c["topic"], "vals": c["vals"]})
    for f in FIELDS:
        v = S.get("filled", {}).get(p["id"], {}).get(f["key"])
        if v is None:
            v = p["handoff"].get(f["key"])
        if not v:
            issues.append({
                "id": f"{p['id']}:handoff:{f['key']}", "pid": p["id"], "type": "handoff",
                "sev": f["sev"],
                "title": f"{f['label']} is missing from the handoff",
                "sub": f["why"], "why": f["why"],
                "fix": {"kind": "field", "key": f["key"], "ph": f["ph"]}})
    for r in p.get("pending", []):
        o = S.get("pendOwners", {}).get(f"{p['id']}|{r['name']}") or r.get("owner")
        if not o:
            issues.append({
                "id": f"{p['id']}:handoff:pend:{r['name']}", "pid": p["id"], "type": "handoff",
                "sev": "med",
                "title": f"Pending result has no owner: {r['name']}",
                "sub": "Result pending, nobody assigned to follow it up",
                "why": "If nobody owns a pending result, it can come back abnormal and go unseen after the patient leaves.",
                "fix": {"kind": "pending", "name": r["name"]}})
    for b in p.get("blockers", []):
        if S.get("cleared", {}).get(p["id"], {}).get(b["id"]):
            continue
        sev = "med"
        if b["blocks"] and (p["dischargeInH"] <= 24 or b["ageH"] >= 24):
            sev = "high"
        elif not b["blocks"] and b["ageH"] < 24:
            sev = "low"
        issues.append({
            "id": f"{p['id']}:blocker:{b['id']}", "pid": p["id"], "type": "blocker",
            "sev": sev, "title": b["label"],
            "sub": f"Waiting on {b['waitingOn']} for {b['ageH']}h. Discharge target in {p['dischargeInH']}h.",
            "why": b["cat"] + (" item that blocks discharge." if b["blocks"] else " item."),
            "bid": b["id"],
            "escalated": bool(S.get("escalated", {}).get(f"{p['id']}|{b['id']}"))})
    issues.sort(key=lambda i: -W[i["sev"]])
    return issues


def risk_of(issues: list[dict]) -> int:
    return sum(W[i["sev"]] for i in issues)


def disch_status(p: dict, issues: list[dict]) -> str:
    if any(i["sev"] == "high" for i in issues):
        return "risk"
    return "watch" if issues else "ready"
