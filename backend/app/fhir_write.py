"""Optional FHIR write-back: Baton APPENDS baton-out-* resources; it never
modifies or deletes any other resource. Off unless FHIR_WRITE=1.
"""

import hashlib
import html
import logging
import os
import re
from datetime import datetime, timezone

from app.fhir_client import FhirClient

log = logging.getLogger(__name__)

FIXTURE_TAG_SYSTEM = "https://github.com/leenadudi/baton"
OUTPUT_TAG_CODE = "baton-output"
OUTPUT_TAG = f"{FIXTURE_TAG_SYSTEM}|{OUTPUT_TAG_CODE}"


def enabled() -> bool:
    return os.environ.get("FHIR_WRITE") == "1"


def _meta() -> dict:
    return {"tag": [
        {"system": FIXTURE_TAG_SYSTEM, "code": "demo-fixture"},
        {"system": FIXTURE_TAG_SYSTEM, "code": OUTPUT_TAG_CODE},
    ]}


def is_output(r: dict) -> bool:
    for tag in (r.get("meta") or {}).get("tag", []):
        if tag.get("system") == FIXTURE_TAG_SYSTEM and tag.get("code") == OUTPUT_TAG_CODE:
            return True
    return str(r.get("id", "")).startswith("baton-out-")


def _slug(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:10]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _id_part(s: str) -> str:
    """FHIR ids allow only [A-Za-z0-9-.] and max 64 chars."""
    return re.sub(r"[^A-Za-z0-9\-.]", "-", s)


async def publish_brief(fhir: FhirClient, text: str) -> dict | None:
    if not enabled():
        return None
    comp_id = f"baton-out-brief-{_stamp()}"
    composition = {
        "resourceType": "Composition",
        "status": "preliminary",
        "type": {"coding": [{"system": "http://loinc.org", "code": "34133-9",
                             "display": "Summary of episode note"}],
                 "text": "Shift handoff brief"},
        "date": _now(),
        "author": [{"display": "Baton"}],
        "title": "Shift handoff brief",
        "section": [{"title": "Brief", "text": {
            "status": "generated",
            "div": f'<div xmlns="http://www.w3.org/1999/xhtml"><pre>{html.escape(text)}</pre></div>',
        }}],
        "meta": _meta(),
    }
    res = await fhir.put("Composition", comp_id, composition)
    return {"id": res["id"], "url": f"{fhir.base_url}/Composition/{res['id']}"}


async def record_adopt(fhir: FhirClient, fid: str, pid: str,
                       topic: str, value: str, text: str) -> dict | None:
    if not enabled() or not fid:
        return None
    comm_id = f"baton-out-{pid}-adopt-{_id_part(topic)}-{_stamp()}"[:64]
    return await fhir.put("Communication", comm_id, {
        "resourceType": "Communication",
        "status": "completed",
        "subject": {"reference": f"Patient/{fid}"},
        "sent": _now(),
        "sender": {"display": "Attending decision (Baton)"},
        "topic": {"text": topic},
        "reasonCode": [{"text": value}],
        "payload": [{"contentString": text}],
        "meta": _meta(),
    })


async def record_fill(fhir: FhirClient, fid: str, pid: str,
                      field: str, value: str) -> dict | None:
    if not enabled() or not fid:
        return None
    return await fhir.put("Task", f"baton-out-{pid}-field-{field}", {
        "resourceType": "Task",
        "status": "completed",
        "intent": "order",
        "code": {"text": "Handoff field"},
        "description": f"{field}={value}",
        "for": {"reference": f"Patient/{fid}"},
        "authoredOn": _now(),
        "meta": _meta(),
    })


async def record_issue_owner(fhir: FhirClient, fid: str, pid: str,
                             issue_id: str, owner: str | None) -> dict | None:
    if not enabled() or not fid:
        return None
    task_id = f"baton-out-{pid}-owner-{_slug(issue_id)}"
    if not owner:
        await fhir.delete("Task", task_id)
        return None
    return await fhir.put("Task", task_id, {
        "resourceType": "Task",
        "status": "requested",
        "intent": "order",
        "code": {"text": "Issue owner"},
        "description": issue_id,
        "owner": {"display": owner},
        "for": {"reference": f"Patient/{fid}"},
        "authoredOn": _now(),
        "meta": _meta(),
    })


async def record_pending_owner(fhir: FhirClient, fid: str, pid: str,
                               name: str, owner: str) -> dict | None:
    if not enabled() or not fid:
        return None
    return await fhir.put("Task", f"baton-out-{pid}-pend-{_slug(name)}", {
        "resourceType": "Task",
        "status": "requested",
        "intent": "order",
        "code": {"text": "Pending owner"},
        "description": name,
        "owner": {"display": owner},
        "for": {"reference": f"Patient/{fid}"},
        "authoredOn": _now(),
        "meta": _meta(),
    })


async def record_blocker_action(fhir: FhirClient, fid: str, pid: str,
                                bid: str, action: str) -> dict | None:
    if not enabled() or not fid:
        return None
    assert action in ("clear", "escalate")
    resource = {
        "resourceType": "Task",
        "status": "completed",
        "intent": "order",
        "code": {"text": "Blocker cleared" if action == "clear" else "Blocker escalated"},
        "description": bid,
        "for": {"reference": f"Patient/{fid}"},
        "authoredOn": _now(),
        "meta": _meta(),
    }
    if action == "escalate":
        resource["priority"] = "stat"
    return await fhir.put("Task", f"baton-out-{pid}-{action}-{bid}", resource)


async def delete_outputs(fhir: FhirClient, fids: list[str]) -> int:
    deleted = 0
    to_delete = []
    for fid in fids:
        for rt in ("Communication", "Task"):
            to_delete += [r for r in await fhir.search(rt, patient=fid, _tag=OUTPUT_TAG, _count=100)
                          if is_output(r)]
    to_delete += [r for r in await fhir.search("Composition", _tag=OUTPUT_TAG, _count=100)
                  if is_output(r)]
    for r in to_delete:
        if not str(r.get("id", "")).startswith("baton-out-"):
            log.warning("skipping delete of non-baton resource %s/%s",
                        r.get("resourceType"), r.get("id"))
            continue
        await fhir.delete(r["resourceType"], r["id"])
        deleted += 1
    return deleted


def outputs_to_state(pid: str, communications: list, tasks: list,
                     base_seq: int = 500) -> dict:
    out = {"added": {}, "filled": {}, "cleared": {}, "escalated": {},
           "pendOwners": {}, "owners": {}}
    notes = []
    for i, c in enumerate(sorted(communications, key=lambda c: c.get("sent", ""))):
        notes.append({
            "role": "Attending decision",
            "author": "Reconciled in Baton",
            "h": 0,
            "text": (c.get("payload") or [{}])[0].get("contentString", ""),
            "tags": [[(c.get("topic") or {}).get("text"),
                      (c.get("reasonCode") or [{}])[0].get("text")]],
            "reconcile": True,
            "seq": base_seq + i + 1,
            "source": {"resourceType": "Communication", "id": c.get("id")},
        })
    if notes:
        out["added"][pid] = notes
    for t in tasks:
        code = (t.get("code") or {}).get("text")
        desc = t.get("description") or ""
        owner = (t.get("owner") or {}).get("display")
        if code == "Handoff field":
            key, _, value = desc.partition("=")
            out["filled"].setdefault(pid, {})[key] = value
        elif code == "Issue owner":
            if owner:
                out["owners"][desc] = owner
        elif code == "Pending owner":
            if owner:
                out["pendOwners"][f"{pid}|{desc}"] = owner
        elif code == "Blocker cleared":
            out["cleared"].setdefault(pid, {})[desc] = True
        elif code == "Blocker escalated":
            out["escalated"][f"{pid}|{desc}"] = True
    return out
