import json
import logging
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / "backend" / ".env")

from app import fhir_panel, fhir_write, panel, rules, state
from app.extract import extract
from app.fhir_client import FhirClient
from app.rules import FIELDS, TOPICS

PATIENT_IDS_FILE = REPO_ROOT / "dataset" / "patient_ids.json"

log = logging.getLogger(__name__)

app = FastAPI(title="Baton API")

fhir = FhirClient()

_cors_origins = {"http://localhost:5173"}
_cors_origins.update(
    o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    try:
        await fhir_panel.ensure_loaded(fhir)
    except Exception:
        pass  # panel falls back to demo data


@app.get("/api/health")
def health_check() -> dict:
    return {"status": "ok", "message": "Baton API is running",
            "panel": fhir_panel.status()}


def _format_name(patient: dict) -> str | None:
    for name in patient.get("name", []):
        given = " ".join(name.get("given", []))
        family = name.get("family", "")
        full = f"{given} {family}".strip()
        if full:
            return full
    return None


@app.get("/fhir/patients")
async def list_patients() -> list[dict]:
    if PATIENT_IDS_FILE.exists():
        return json.loads(PATIENT_IDS_FILE.read_text())
    patients = await fhir.search("Patient", _count=20)
    return [
        {
            "fhirPatientId": f"Patient/{p.get('id')}",
            "name": _format_name(p),
            "birthDate": p.get("birthDate"),
            "base_url": fhir.base_url,
        }
        for p in patients
    ]


@app.get("/fhir/patients/{patient_id}/chart")
async def get_patient_chart(patient_id: str) -> dict:
    chart = await fhir.patient_chart(patient_id)
    patient = chart.pop("Patient")
    counts = {rt: len(resources) for rt, resources in chart.items()}
    return {"patient": patient, "resources": chart, "counts": counts}


class ExtractRequest(BaseModel):
    text: str
    author: str | None = None
    role: str | None = None


@app.post("/extract")
async def extract_note(body: ExtractRequest) -> dict:
    """Note text in -> tags out. Tags are ["topic", "value"] pairs,
    the same shape the rule engine consumes on notes."""
    result = await extract(body.text, role=body.role)
    result["tags"] = [[t["topic"], t["value"]] for t in result["tags"]]
    return result


# ---------- panel + demo mutation routes (PRD 8.1) ----------


class NoteIn(BaseModel):
    role: str
    author: str | None = None
    text: str | None = None
    topic: str | None = None
    value: str | None = None
    reconcile: bool = False


class IssuePatch(BaseModel):
    action: Literal["owner", "fill", "pendingOwner", "clear", "escalate", "adopt"]
    value: str | None = None


async def _panel_ready() -> None:
    await fhir_panel.ensure_loaded(fhir)


def _patient_or_404(pid: str) -> dict:
    p = panel.get_patient(pid)
    if p is None:
        raise HTTPException(404, f"unknown patient: {pid}")
    return p


def _fid(p: dict) -> str | None:
    ref = p.get("fhirPatientId") or ""
    return ref.split("/", 1)[1] if ref.startswith("Patient/") else None


def _issue_or_404(pid: str, issue_id: str) -> dict:
    issue = next((i for i in rules.get_issues(_patient_or_404(pid), panel.effective_state())
                  if i["id"] == issue_id), None)
    if issue is None:
        raise HTTPException(404, f"unknown issue: {issue_id}")
    return issue


@app.get("/patients")
async def list_panel_patients() -> list[dict]:
    await _panel_ready()
    return [panel.build_patient(p) for p in panel.load_patients()]


@app.get("/patients/{pid}")
async def get_panel_patient(pid: str) -> dict:
    await _panel_ready()
    return panel.build_patient(_patient_or_404(pid))


@app.post("/patients/{pid}/notes")
async def add_note(pid: str, body: NoteIn) -> dict:
    await _panel_ready()
    p = _patient_or_404(pid)
    if body.topic:
        if body.topic not in TOPICS or body.value not in TOPICS[body.topic]["values"]:
            raise HTTPException(422, f"invalid topic/value: {body.topic}={body.value}")
        tags = [[body.topic, body.value]]
        text = body.text or f"{TOPICS[body.topic]['label']}: {body.value}."
    elif body.text:
        tags = []
        if os.environ.get("OPENAI_API_KEY"):
            extracted = await extract(body.text, body.role)
            tags = [[t["topic"], t["value"]] for t in extracted["tags"]]
        text = body.text
    else:
        raise HTTPException(422, "provide topic+value or free text")
    note = {"role": body.role, "author": body.author or f"{body.role} (you)",
            "text": text, "tags": tags}
    if body.reconcile:
        note["reconcile"] = True
    panel.add_note(pid, note)
    suffix = f" ({TOPICS[body.topic]['label']}: {body.value})" if body.topic else ""
    # A reconciling note (rules.py's barrier) genuinely resolves a conflict —
    # but only if it actually carries a tag for that topic; an untagged
    # reconcile=true note has no effect on any conflict. Any other note is a
    # new instruction, which can introduce a conflict as easily as settle one.
    state.log_act(pid, f"Added {body.role} note{suffix}",
                  resolved=bool(body.reconcile and tags))
    return panel.build_patient(p)


@app.patch("/issues/{issue_id}")
async def patch_issue(issue_id: str, body: IssuePatch) -> dict:
    await _panel_ready()
    parts = issue_id.split(":", 2)
    pid = parts[0] if len(parts) == 3 else issue_id.split(":")[0]
    p = _patient_or_404(pid)
    S = state.STATE
    kind, rest = (parts[1], parts[2]) if len(parts) == 3 else (None, None)

    if body.action == "owner":
        issue = _issue_or_404(pid, issue_id)
        if body.value:
            S["owners"][issue_id] = body.value
            state.log_act(pid, f'Assigned "{issue["title"]}" to {body.value}')
        else:
            S["owners"][issue_id] = ""  # tombstone masks a chart-loaded owner
        await _write(fhir_write.record_issue_owner(fhir, _fid(p) or "", pid,
                                                   issue_id, body.value), pid)
    elif body.action == "fill":
        if kind != "handoff" or rest not in {f["key"] for f in FIELDS}:
            raise HTTPException(404, f"unknown issue: {issue_id}")
        _issue_or_404(pid, issue_id)
        if not body.value:
            raise HTTPException(422, "value is required to fill a handoff field")
        S["filled"].setdefault(pid, {})[rest] = body.value
        label = next(f["label"] for f in FIELDS if f["key"] == rest)
        state.log_act(pid, f"Added {label} to handoff")
        await _write(fhir_write.record_fill(fhir, _fid(p) or "", pid,
                                            rest, body.value), pid)
    elif body.action == "pendingOwner":
        if kind != "handoff" or not rest or not rest.startswith("pend:"):
            raise HTTPException(404, f"unknown issue: {issue_id}")
        _issue_or_404(pid, issue_id)
        name = rest[len("pend:"):]
        if not body.value:
            raise HTTPException(422, "value is required to assign an owner")
        S["pendOwners"][f"{pid}|{name}"] = body.value
        state.log_act(pid, f"Assigned {name} follow-up to {body.value}")
        await _write(fhir_write.record_pending_owner(fhir, _fid(p) or "", pid,
                                                     name, body.value), pid)
    elif body.action in ("clear", "escalate"):
        if kind != "blocker" or not rest:
            raise HTTPException(404, f"unknown issue: {issue_id}")
        blocker = next((b for b in p["blockers"] if b["id"] == rest), None)
        if blocker is None:
            raise HTTPException(404, f"unknown issue: {issue_id}")
        if body.action == "clear":
            S["cleared"].setdefault(pid, {})[rest] = True
            state.log_act(pid, f"Cleared blocker: {blocker['label']}")
        else:
            S["escalated"][f"{pid}|{rest}"] = True
            # Not resolved: escalating raises urgency, it doesn't close the blocker.
            state.log_act(pid, f"Escalated blocker: {blocker['label']}", resolved=False)
        await _write(fhir_write.record_blocker_action(fhir, _fid(p) or "", pid,
                                                      rest, body.action), pid)
    elif body.action == "adopt":
        if kind != "conflict" or rest not in TOPICS:
            raise HTTPException(404, f"unknown issue: {issue_id}")
        topic = rest
        if body.value not in TOPICS[topic]["values"]:
            raise HTTPException(422, f"invalid value for {topic}: {body.value}")
        label = TOPICS[topic]["label"]
        text = (f"Reconciled {label}: proceed with {body.value}. "
                "Earlier conflicting instructions are superseded.")
        note = {"role": "Attending decision", "author": "Reconciled in Baton",
                "text": text, "tags": [[topic, body.value]], "reconcile": True}
        panel.add_note(pid, note)
        res = await _write(fhir_write.record_adopt(fhir, _fid(p) or "", pid,
                                                   topic, body.value, text), pid)
        if res:
            note["source"] = {"resourceType": "Communication", "id": res.get("id")}
        state.log_act(pid, f"Reconciled {label} to {body.value}")
    return panel.build_patient(p)


async def _write(coro, pid: str):
    """Run a fhir_write call; failures are logged, never fatal to the local state."""
    try:
        return await coro
    except Exception as exc:
        log.warning("FHIR write failed: %s", exc)
        state.log_act(pid, f"FHIR write failed: {exc}", resolved=False)
        return None


@app.post("/brief/publish")
async def publish_brief() -> dict:
    if not fhir_write.enabled():
        raise HTTPException(409, "FHIR_WRITE is off")
    res = await fhir_write.publish_brief(fhir, panel.brief_text())
    return {"id": res["id"], "url": res["url"]}


@app.get("/brief", response_class=PlainTextResponse)
async def get_brief() -> str:
    await _panel_ready()
    return panel.brief_text()


@app.post("/demo/reset")
async def demo_reset() -> dict:
    state.reset()
    result: dict = {"status": "ok"}
    if fhir_write.enabled():
        fids = [f for f in (_fid(p) for p in panel.load_patients()) if f]
        result["deleted"] = await fhir_write.delete_outputs(fhir, fids)
        fhir_panel.force_invalidate()
        await fhir_panel.ensure_loaded(fhir)
    return result


@app.post("/demo/refresh")
async def demo_refresh() -> dict:
    refreshed = fhir_panel.invalidate()
    await fhir_panel.ensure_loaded(fhir)
    return {**fhir_panel.status(), "refreshed": refreshed}


@app.get("/fhir/status")
async def fhir_status() -> dict:
    try:
        async with httpx.AsyncClient(timeout=30,
                                     headers={"Accept": "application/fhir+json"}) as client:
            resp = await client.get(f"{fhir.base_url}/metadata")
    except httpx.TransportError as exc:
        return {"base_url": fhir.base_url, "error": str(exc)}
    if resp.status_code >= 400:
        return {"base_url": fhir.base_url, "error": f"HTTP {resp.status_code}"}
    try:
        fhir_version = resp.json().get("fhirVersion")
    except ValueError:
        return {"base_url": fhir.base_url, "error": "non-JSON response"}
    return {"base_url": fhir.base_url, "fhirVersion": fhir_version}
