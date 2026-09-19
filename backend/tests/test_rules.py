import copy

from app.demo_patients import DEMO_PATIENTS
from app.rules import assign_seq, disch_status, find_conflicts, get_issues


def patient(pid):
    return next(p for p in DEMO_PATIENTS if p["id"] == pid)


def conflict_topics(p):
    return {c["topic"] for c in find_conflicts(p)}


def issue_ids(p):
    return {i["id"] for i in get_issues(p)}


def test_p1_conflicts():
    p1 = patient("p1")
    topics = conflict_topics(p1)
    assert {"weight_bearing", "anticoagulation", "destination"} <= topics
    assert "diet" not in topics


def test_p1_issues():
    p1 = patient("p1")
    ids = issue_ids(p1)
    assert "p1:handoff:followUpOwner" in ids
    assert "p1:handoff:pend:Type and screen" in ids
    by_id = {i["id"]: i for i in get_issues(p1)}
    # b1: blocks discharge and ageH 31 >= 24 -> high
    assert by_id["p1:blocker:b1"]["sev"] == "high"
    # b2: blocks but dischargeInH 30 > 24 and ageH 6 < 24 -> med
    assert by_id["p1:blocker:b2"]["sev"] == "med"


def test_p2_conflicts_and_code_status():
    p2 = patient("p2")
    assert {"fluids", "diet"} <= conflict_topics(p2)
    assert "p2:handoff:codeStatus" in issue_ids(p2)


def test_p3_only_family_contact():
    assert issue_ids(patient("p3")) == {"p3:handoff:familyContact"}


def test_p6_no_issues():
    assert get_issues(patient("p6")) == []
    assert disch_status(patient("p6"), []) == "ready"


def test_reconcile_clears_conflict():
    p1 = copy.deepcopy(patient("p1"))
    note = {"role": "Attending decision", "author": "Reconciled in Baton", "h": 0,
            "text": "Reconciled Anticoagulation: proceed with hold.",
            "tags": [["anticoagulation", "hold"]], "reconcile": True}
    p1["notes"].append(note)
    assign_seq(p1["notes"])
    topics = conflict_topics(p1)
    assert "anticoagulation" not in topics
    assert {"weight_bearing", "destination"} <= topics
