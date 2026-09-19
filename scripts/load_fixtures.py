#!/usr/bin/env python3
"""Author Baton demo fixtures onto the mapped FHIR patients.

Reads the six PRD section 5 personas from backend/app/demo_patients.py (the
single source of truth -- fixture JSON is generated, never hand-edited) and
writes FHIR resources so each mapped patient carries the exact notes,
handoff fields, and blockers the prototype shows. The Baton backend itself
never writes to FHIR; this script is the only writer.

Usage:
    python scripts/load_fixtures.py --base-url https://hapi.fhir.org/baseR4
    python scripts/load_fixtures.py --dump-only   # write dataset/fixtures only

Encodings (agreed with the backend; keep docs/amy_handoff.md in sync):
    note          -> DocumentReference: LOINC 34109-9, category[0].text=role,
                     author[0]={reference Practitioner, display author},
                     date = now - h, content[0].attachment.data = base64 text
    blocker       -> Task: status=requested, intent=order,
                     priority="urgent" iff blocks else "routine",
                     code.text=cat, description=label, owner.display=waitingOn,
                     authoredOn = now - ageH
    pending result-> Task: code.text="Pending result", description=name,
                     owner.display=owner (omitted when empty -> unowned flag)
    codeStatus    -> Consent: scope=adr, category=acd,
                     provision.code[0].text = value (omitted when empty)
    allergies     -> AllergyIntolerance: code.text = value,
                     "NKDA" -> "No known drug allergies" (omitted when empty)
    familyContact -> Patient.contact[0].name.text = value
                     (contact stripped when empty)
    followUpOwner -> Task: code.text="Follow-up owner", owner.display=value
    medRec        -> Task: code.text="Medication reconciliation",
                     status="completed", description=value
    care team     -> Practitioner + PractitionerRole per author/role,
                     CareTeam per patient, ServiceRequest per consulted role

All resources use fixed ids (baton-<pid>-...) loaded with PUT, so reruns
after a public-HAPI wipe are idempotent. Before loading, the script deletes
existing patient-scoped resources of the types it controls
(DocumentReference, AllergyIntolerance, Task, Consent, Goal, CareTeam,
ServiceRequest) on the mapped patients so stale Synthea content cannot
contradict a persona (e.g. Elena's deliberately-missing allergies).
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.demo_patients import DEMO_PATIENTS  # noqa: E402

try:
    import httpx
except ModuleNotFoundError:  # --dump-only works without it
    httpx = None

DEMO_MAP_FILE = REPO_ROOT / "dataset" / "demo_patients.json"
FIXTURES_DIR = REPO_ROOT / "dataset" / "fixtures"
FHIR_JSON = {"Content-Type": "application/fhir+json"}
FHIR_ACCEPT = {"Accept": "application/fhir+json"}

# every Baton-authored fixture carries this tag so the backend can select demo
# content without relying on ids (public HAPI refuses deletes of referenced
# resources, so stale Synthea resources cannot be removed from the chart)
BATON_TAG = {"meta": {"tag": [{"system": "https://github.com/leenadudi/baton",
                               "code": "demo-fixture"}]}}

# patient-scoped resource types we own; wiped on mapped patients before load
CONTROLLED_TYPES = [
    "DocumentReference", "AllergyIntolerance", "Task", "Consent",
    "Goal", "CareTeam", "ServiceRequest",
]

MAX_RETRIES = 3


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def iso_hours_ago(hours: float) -> str:
    t = datetime.now(timezone.utc) - timedelta(hours=hours)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def patient_ref(demo_map: dict, pid: str) -> dict:
    return {"reference": demo_map[pid]["fhirPatientId"]}


def practitioner_id(author: str) -> str:
    return f"baton-prac-{slug(author)}"


def role_id(role: str) -> str:
    return f"baton-role-{slug(role)}"


def build_practitioner(author: str) -> dict:
    return {
        "resourceType": "Practitioner",
        "id": practitioner_id(author),
        "name": [{"text": author}],
    }


def build_role(role: str, author: str) -> dict:
    return {
        "resourceType": "PractitionerRole",
        "id": role_id(role),
        "practitioner": {"reference": f"Practitioner/{practitioner_id(author)}",
                         "display": author},
        "code": [{"text": role}],
    }


def build_note(pid: str, idx: int, note: dict, demo_map: dict) -> dict:
    return {
        "resourceType": "DocumentReference",
        "id": f"baton-{pid}-note-{idx}",
        "status": "current",
        "type": {"coding": [{"system": "http://loinc.org",
                             "code": "34109-9", "display": "Note"}]},
        "category": [{"text": note["role"]}],
        "subject": patient_ref(demo_map, pid),
        "date": iso_hours_ago(note["h"]),
        "author": [{"reference": f"Practitioner/{practitioner_id(note['author'])}",
                    "display": note["author"]}],
        "description": "Baton demo note",
        "content": [{"attachment": {
            "contentType": "text/plain",
            "data": base64.b64encode(note["text"].encode()).decode(),
        }}],
    }


def build_blocker_task(pid: str, blocker: dict, demo_map: dict) -> dict:
    return {
        "resourceType": "Task",
        "id": f"baton-{pid}-blocker-{blocker['id']}",
        "status": "requested",
        "intent": "order",
        # "blocks discharge" is encoded as priority=urgent
        "priority": "urgent" if blocker.get("blocks") else "routine",
        "code": {"text": blocker["cat"]},
        "description": blocker["label"],
        "for": patient_ref(demo_map, pid),
        "authoredOn": iso_hours_ago(blocker["ageH"]),
        "owner": {"display": blocker["waitingOn"]},
    }


def build_pending_task(pid: str, idx: int, pending: dict, demo_map: dict) -> dict:
    task = {
        "resourceType": "Task",
        "id": f"baton-{pid}-pending-{idx}",
        "status": "requested",
        "intent": "order",
        "code": {"text": "Pending result"},
        "description": pending["name"],
        "for": patient_ref(demo_map, pid),
        "authoredOn": iso_hours_ago(6),
    }
    if pending.get("owner"):
        task["owner"] = {"display": pending["owner"]}
    return task


def build_code_status(pid: str, value: str, demo_map: dict) -> dict:
    return {
        "resourceType": "Consent",
        "id": f"baton-{pid}-consent-codestatus",
        "status": "active",
        "scope": {"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/consentscope",
            "code": "adr"}]},
        "category": [{"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/consentcategorycodes",
            "code": "acd", "display": "Advance Directive"}]}],
        "patient": patient_ref(demo_map, pid),
        "dateTime": iso_hours_ago(48),
        "provision": {"type": "permit", "code": [{"text": value}]},
    }


def build_allergy(pid: str, idx: int, value: str, demo_map: dict) -> dict:
    if value == "NKDA":
        value = "No known drug allergies"
    return {
        "resourceType": "AllergyIntolerance",
        "id": f"baton-{pid}-allergy-{idx}",
        "clinicalStatus": {"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
            "code": "active"}]},
        "code": {"text": value},
        "patient": patient_ref(demo_map, pid),
        "recordedDate": iso_hours_ago(72),
    }


def build_field_task(pid: str, kind: str, value: str, demo_map: dict) -> dict:
    task = {
        "resourceType": "Task",
        "id": f"baton-{pid}-{kind}",
        "intent": "order",
        "for": patient_ref(demo_map, pid),
        "authoredOn": iso_hours_ago(24),
    }
    if kind == "followup":
        task.update({"status": "accepted",
                     "code": {"text": "Follow-up owner"},
                     "description": value,
                     "owner": {"display": value}})
    else:  # medrec
        task.update({"status": "completed",
                     "code": {"text": "Medication reconciliation"},
                     "description": value})
    return task


def build_care_team(pid: str, roles: dict, demo_map: dict) -> dict:
    return {
        "resourceType": "CareTeam",
        "id": f"baton-{pid}-careteam",
        "status": "active",
        "subject": patient_ref(demo_map, pid),
        "participant": [
            {"role": [{"text": role}],
             "member": {"reference": f"Practitioner/{practitioner_id(author)}",
                        "display": author}}
            for role, author in roles.items()
        ],
    }


def build_service_request(pid: str, idx: int, role: str, author: str,
                          demo_map: dict) -> dict:
    return {
        "resourceType": "ServiceRequest",
        "id": f"baton-{pid}-consult-{idx}",
        "status": "active",
        "intent": "order",
        "code": {"text": f"{role} consult"},
        "subject": patient_ref(demo_map, pid),
        "authoredOn": iso_hours_ago(48),
        "requester": {"reference": f"Practitioner/{practitioner_id(author)}",
                      "display": author},
    }


def persona_roles(persona: dict) -> dict:
    """role -> author for every distinct role on the persona's notes."""
    roles = {}
    for note in persona["notes"]:
        roles.setdefault(note["role"], note["author"])
    return roles


def build_fixtures(demo_map: dict) -> tuple[dict[str, list[dict]], dict]:
    """Return ({pid: [resources]}, {shared practitioners/roles})."""
    by_patient: dict[str, list[dict]] = {}
    shared: dict[str, dict] = {}
    for persona in DEMO_PATIENTS:
        pid = persona["id"]
        if pid not in demo_map:
            print(f"  {pid} ({persona['name']}): no FHIR mapping, skipped")
            continue
        resources: list[dict] = []
        roles = persona_roles(persona)
        for role, author in roles.items():
            shared[practitioner_id(author)] = build_practitioner(author)
            shared[role_id(role)] = build_role(role, author)

        for i, note in enumerate(persona["notes"], 1):
            resources.append(build_note(pid, i, note, demo_map))
        for blocker in persona.get("blockers", []):
            resources.append(build_blocker_task(pid, blocker, demo_map))
        for i, pending in enumerate(persona.get("pending", []), 1):
            resources.append(build_pending_task(pid, i, pending, demo_map))

        handoff = persona["handoff"]
        if handoff.get("codeStatus"):
            resources.append(build_code_status(pid, handoff["codeStatus"], demo_map))
        if handoff.get("allergies"):
            for i, allergy in enumerate(handoff["allergies"].split(";"), 1):
                resources.append(build_allergy(pid, i, allergy.strip(), demo_map))
        if handoff.get("followUpOwner"):
            resources.append(build_field_task(pid, "followup",
                                              handoff["followUpOwner"], demo_map))
        if handoff.get("medRec"):
            resources.append(build_field_task(pid, "medrec",
                                              handoff["medRec"], demo_map))

        resources.append(build_care_team(pid, roles, demo_map))
        for i, (role, author) in enumerate(roles.items(), 1):
            resources.append(build_service_request(pid, i, role, author, demo_map))
        by_patient[pid] = resources
    tag = BATON_TAG["meta"]["tag"][0]
    for res in [r for rs in by_patient.values() for r in rs] + list(shared.values()):
        res.setdefault("meta", {}).setdefault("tag", []).append(tag)
    return by_patient, shared


def dump_fixtures(by_patient: dict[str, list[dict]], shared: dict) -> None:
    for pid, resources in by_patient.items():
        out_dir = FIXTURES_DIR / pid
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, res in enumerate(resources, 1):
            path = out_dir / f"{i:02d}-{res['resourceType']}-{res['id']}.json"
            path.write_text(json.dumps(res, indent=2) + "\n")
    for res in shared.values():
        out_dir = FIXTURES_DIR / "shared"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{res['resourceType']}-{res['id']}.json").write_text(
            json.dumps(res, indent=2) + "\n")


def request(client: httpx.Client, method: str, url: str, **kwargs) -> dict | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            print(f"    {method} {url}: transport error (attempt {attempt}): {exc}")
            if attempt == MAX_RETRIES:
                return None
            time.sleep(2 ** attempt)
            continue
        if resp.status_code < 400:
            if resp.status_code == 204 or not resp.content:
                return {}
            return resp.json()
        print(f"    {method} {url}: HTTP {resp.status_code} {resp.text[:300]}")
        if 400 <= resp.status_code < 500:
            return None
        if attempt == MAX_RETRIES:
            return None
        time.sleep(2 ** attempt)
    return None


def wipe_controlled(client: httpx.Client, base: str, patient_ref_str: str) -> int:
    """Delete existing resources of CONTROLLED_TYPES on one patient."""
    pid = patient_ref_str.split("/", 1)[1]
    deleted = 0
    for rtype in CONTROLLED_TYPES:
        bundle = request(client, "GET", f"{base}/{rtype}",
                         params={"patient": pid, "_count": 100},
                         headers=FHIR_ACCEPT)
        if not bundle:
            continue
        for entry in bundle.get("entry", []):
            res = entry.get("resource", {})
            if res.get("id") and request(
                    client, "DELETE", f"{base}/{rtype}/{res['id']}",
                    headers=FHIR_ACCEPT) is not None:
                deleted += 1
    return deleted


def update_patient(client: httpx.Client, base: str, persona: dict,
                   fhir_patient_id: str) -> None:
    """Set display name + familyContact on the mapped Patient resource."""
    pid = fhir_patient_id.split("/", 1)[1]
    patient = request(client, "GET", f"{base}/Patient/{pid}", headers=FHIR_ACCEPT)
    if not patient:
        return
    first, _, last = persona["name"].partition(" ")
    patient["name"] = [{"use": "official", "text": persona["name"],
                        "family": last.strip() or persona["name"],
                        "given": [first]}]
    contact = persona["handoff"].get("familyContact")
    if contact:
        patient["contact"] = [{
            "relationship": [{"text": contact}],
            "name": {"text": contact},
        }]
    else:
        patient.pop("contact", None)
    request(client, "PUT", f"{base}/Patient/{pid}", json=patient, headers=FHIR_JSON)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url",
                        default=os.environ.get("FHIR_BASE_URL",
                                               "https://hapi.fhir.org/baseR4"),
                        help="FHIR server base URL (env FHIR_BASE_URL)")
    parser.add_argument("--demo", default=str(DEMO_MAP_FILE),
                        help="Persona -> Patient mapping JSON")
    parser.add_argument("--dump-only", action="store_true",
                        help="Write dataset/fixtures/ without touching a server")
    args = parser.parse_args()

    demo_map = {k: v for k, v in
                json.loads(Path(args.demo).read_text()).items()
                if not k.startswith("_")}
    by_patient, shared = build_fixtures(demo_map)
    dump_fixtures(by_patient, shared)
    total = sum(len(r) for r in by_patient.values()) + len(shared)
    print(f"Wrote {total} fixtures to {FIXTURES_DIR}")
    if args.dump_only:
        return 0
    if httpx is None:
        print("httpx is required for loading (pip install -r backend/requirements.txt)",
              file=sys.stderr)
        return 1

    base = args.base_url.rstrip("/")
    personas = {p["id"]: p for p in DEMO_PATIENTS}
    print(f"Loading fixtures to {base}")
    failed = 0
    with httpx.Client(timeout=60) as client:
        for res in shared.values():
            if request(client, "PUT", f"{base}/{res['resourceType']}/{res['id']}",
                       json=res, headers=FHIR_JSON) is None:
                failed += 1
        for pid, resources in by_patient.items():
            ref = demo_map[pid]["fhirPatientId"]
            persona = personas[pid]
            print(f"[{pid}] {persona['name']} -> {ref}")
            deleted = wipe_controlled(client, base, ref)
            if deleted:
                print(f"    wiped {deleted} pre-existing controlled resources")
            update_patient(client, base, persona, ref)
            for res in resources:
                if request(client, "PUT",
                           f"{base}/{res['resourceType']}/{res['id']}",
                           json=res, headers=FHIR_JSON) is None:
                    failed += 1
                    print(f"    FAILED {res['resourceType']}/{res['id']}")
            print(f"    loaded {len(resources)} resources")
    print(f"Done ({failed} failures)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
