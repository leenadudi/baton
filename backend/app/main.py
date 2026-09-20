import json
import logging
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / "backend" / ".env")

from app import fhir_panel, fhir_write, panel, rules, state
from app import store as store_mod
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


# ---------- auth: email + password, bearer tokens (docs/schema.md) ----------


class RegisterIn(BaseModel):
    email: str
    password: str
    name: str


class LoginIn(BaseModel):
    email: str
    password: str


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def _optional_doctor(authorization: str | None = Header(default=None)) -> dict | None:
    token = _bearer(authorization)
    return store_mod.get_store().user_for_token(token) if token else None


def _require_doctor(doctor: dict | None = Depends(_optional_doctor)) -> dict:
    if doctor is None:
        raise HTTPException(401, "sign in required")
    return doctor


@app.post("/auth/register", status_code=201)
def register(body: RegisterIn) -> dict:
    st = store_mod.get_store()
    email, name = body.email.strip().lower(), body.name.strip()
    if "@" not in email:
        raise HTTPException(422, "a valid email is required")
    if not name:
        raise HTTPException(422, "name is required")
    if len(body.password) < store_mod.MIN_PASSWORD_LEN:
        raise HTTPException(422, "password must be at least "
                            f"{store_mod.MIN_PASSWORD_LEN} characters")
    try:
        doctor = st.create_user(email, name, body.password)
    except store_mod.StoreError as exc:
        raise HTTPException(409, str(exc))
    return {"token": st.create_token(doctor["id"]), "doctor": doctor}


@app.post("/auth/login")
def login(body: LoginIn) -> dict:
    st = store_mod.get_store()
    u = st.user_by_email(body.email.strip().lower())
    if u is None or not st.check_password(u, body.password):
        raise HTTPException(401, "invalid email or password")
    doctor = {"id": u["id"], "name": u["name"], "email": u["email"]}
    return {"token": st.create_token(doctor["id"]), "doctor": doctor}


@app.get("/auth/me")
def auth_me(doctor: dict = Depends(_require_doctor)) -> dict:
    return doctor


@app.post("/auth/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    token = _bearer(authorization)
    if token:
        store_mod.get_store().revoke_token(token)
    return {"status": "ok"}


@app.get("/doctors")
def list_doctors() -> list:
    return store_mod.get_store().list_doctors()


# ---------- panel + demo mutation routes (PRD 8.1) ----------


class _Ctx:
    """Request context: the demo-state scope + the signed-in doctor (if any)."""

    def __init__(self, scope: str, s: dict, doctor: dict | None) -> None:
        self.scope, self.s, self.doctor = scope, s, doctor


def _ctx(doctor: dict | None = Depends(_optional_doctor),
         x_session_id: str | None = Header(default=None)):
    """Signed-in clinicians share the unit; guests get a session sandbox."""
    st = store_mod.get_store()
    scope = store_mod.UNIT_SCOPE if doctor else store_mod.session_scope(x_session_id)
    s = st.get_state(scope)
    yield _Ctx(scope, s, doctor)
    st.save_state(scope, s)
    st.prune()


def _record(ctx: _Ctx, pid: str | None, text: str, action: str,
            target: str | None = None, resolved: bool = True) -> None:
    doctor_name = ctx.doctor["name"] if ctx.doctor else "Guest"
    if pid:
        state.log_act(ctx.s, pid, text, by=doctor_name,
                      by_id=ctx.doctor["id"] if ctx.doctor else None,
                      resolved=resolved)
    store_mod.get_store().record_action(ctx.scope, {
        "at": int(time.time() * 1000),
        "doctorId": ctx.doctor["id"] if ctx.doctor else None,
        "doctorName": doctor_name,
        "patientId": pid, "action": action, "target": target, "text": text,
        "resolved": resolved})


@app.get("/activity")
def list_activity(patient: str | None = None, doctor: str | None = None,
                  ctx: _Ctx = Depends(_ctx)) -> list:
    """Audit trail for the caller's scope, newest first."""
    return store_mod.get_store().list_actions(
        ctx.scope, patient_id=patient, doctor_id=doctor)


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


def _issue_or_404(pid: str, issue_id: str, s: dict) -> dict:
    issue = next((i for i in rules.get_issues(_patient_or_404(pid),
                                              panel.effective_state(s))
                  if i["id"] == issue_id), None)
    if issue is None:
        raise HTTPException(404, f"unknown issue: {issue_id}")
    return issue


@app.get("/patients")
async def list_panel_patients(ctx: _Ctx = Depends(_ctx)) -> list[dict]:
    await _panel_ready()
    return [panel.build_patient(p, ctx.s) for p in panel.load_patients()]


@app.get("/patients/{pid}")
async def get_panel_patient(pid: str, ctx: _Ctx = Depends(_ctx)) -> dict:
    await _panel_ready()
    return panel.build_patient(_patient_or_404(pid), ctx.s)


@app.post("/patients/{pid}/notes")
async def add_note(pid: str, body: NoteIn, ctx: _Ctx = Depends(_ctx)) -> dict:
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
    author = body.author or (ctx.doctor["name"] if ctx.doctor
                             else f"{body.role} (you)")
    note = {"role": body.role, "author": author, "text": text, "tags": tags}
    if body.reconcile:
        note["reconcile"] = True
    panel.add_note(pid, note, ctx.s)
    suffix = f" ({TOPICS[body.topic]['label']}: {body.value})" if body.topic else ""
    # A reconciling note (rules.py's barrier) genuinely resolves a conflict —
    # but only if it actually carries a tag for that topic; an untagged
    # reconcile=true note has no effect on any conflict. Any other note is a
    # new instruction, which can introduce a conflict as easily as settle one.
    _record(ctx, pid, f"Added {body.role} note{suffix}", "addNote",
            resolved=bool(body.reconcile and tags))
    return panel.build_patient(p, ctx.s)


@app.patch("/issues/{issue_id}")
async def patch_issue(issue_id: str, body: IssuePatch,
                      ctx: _Ctx = Depends(_ctx)) -> dict:
    await _panel_ready()
    parts = issue_id.split(":", 2)
    pid = parts[0] if len(parts) == 3 else issue_id.split(":")[0]
    p = _patient_or_404(pid)
    S = ctx.s
    kind, rest = (parts[1], parts[2]) if len(parts) == 3 else (None, None)

    if body.action == "owner":
        issue = _issue_or_404(pid, issue_id, S)
        if body.value:
            S["owners"][issue_id] = body.value
            _record(ctx, pid, f'Assigned "{issue["title"]}" to {body.value}',
                    "owner", issue_id)
        else:
            S["owners"][issue_id] = ""  # tombstone masks a chart-loaded owner
            _record(ctx, pid, f'Unassigned "{issue["title"]}"', "owner", issue_id)
        await _write(ctx, fhir_write.record_issue_owner(fhir, _fid(p) or "", pid,
                                                        issue_id, body.value), pid)
    elif body.action == "fill":
        if kind != "handoff" or rest not in {f["key"] for f in FIELDS}:
            raise HTTPException(404, f"unknown issue: {issue_id}")
        _issue_or_404(pid, issue_id, S)
        if not body.value:
            raise HTTPException(422, "value is required to fill a handoff field")
        S["filled"].setdefault(pid, {})[rest] = body.value
        label = next(f["label"] for f in FIELDS if f["key"] == rest)
        _record(ctx, pid, f"Added {label} to handoff: {body.value}",
                "fill", issue_id)
        await _write(ctx, fhir_write.record_fill(fhir, _fid(p) or "", pid,
                                                 rest, body.value), pid)
    elif body.action == "pendingOwner":
        if kind != "handoff" or not rest or not rest.startswith("pend:"):
            raise HTTPException(404, f"unknown issue: {issue_id}")
        _issue_or_404(pid, issue_id, S)
        name = rest[len("pend:"):]
        if not body.value:
            raise HTTPException(422, "value is required to assign an owner")
        S["pendOwners"][f"{pid}|{name}"] = body.value
        _record(ctx, pid, f"Assigned {name} follow-up to {body.value}",
                "pendingOwner", issue_id)
        await _write(ctx, fhir_write.record_pending_owner(fhir, _fid(p) or "", pid,
                                                          name, body.value), pid)
    elif body.action in ("clear", "escalate"):
        if kind != "blocker" or not rest:
            raise HTTPException(404, f"unknown issue: {issue_id}")
        blocker = next((b for b in p["blockers"] if b["id"] == rest), None)
        if blocker is None:
            raise HTTPException(404, f"unknown issue: {issue_id}")
        if body.action == "clear":
            S["cleared"].setdefault(pid, {})[rest] = True
            _record(ctx, pid, f"Cleared blocker: {blocker['label']}",
                    "clear", issue_id)
        else:
            S["escalated"][f"{pid}|{rest}"] = True
            # Not resolved: escalating raises urgency, it doesn't close the blocker.
            _record(ctx, pid, f"Escalated blocker: {blocker['label']}",
                    "escalate", issue_id, resolved=False)
        await _write(ctx, fhir_write.record_blocker_action(fhir, _fid(p) or "", pid,
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
        note = {"role": "Attending decision",
                "author": ctx.doctor["name"] if ctx.doctor else "Reconciled in Baton",
                "text": text, "tags": [[topic, body.value]], "reconcile": True}
        panel.add_note(pid, note, S)
        res = await _write(ctx, fhir_write.record_adopt(fhir, _fid(p) or "", pid,
                                                        topic, body.value, text), pid)
        if res:
            note["source"] = {"resourceType": "Communication", "id": res.get("id")}
        _record(ctx, pid, f"Reconciled {label} to {body.value}",
                "adopt", issue_id)
    return panel.build_patient(p, ctx.s)


async def _write(ctx: _Ctx, coro, pid: str):
    """Run a fhir_write call; failures are logged, never fatal to the local state."""
    try:
        return await coro
    except Exception as exc:
        log.warning("FHIR write failed: %s", exc)
        _record(ctx, pid, f"FHIR write failed: {exc}", "fhirWrite",
                resolved=False)
        return None


@app.post("/brief/publish")
async def publish_brief(ctx: _Ctx = Depends(_ctx)) -> dict:
    if not fhir_write.enabled():
        raise HTTPException(409, "FHIR_WRITE is off")
    res = await fhir_write.publish_brief(fhir, panel.brief_text(ctx.s))
    return {"id": res["id"], "url": res["url"]}


@app.get("/brief", response_class=PlainTextResponse)
async def get_brief(ctx: _Ctx = Depends(_ctx)) -> str:
    await _panel_ready()
    return panel.brief_text(ctx.s)


@app.post("/demo/reset")
async def demo_reset(ctx: _Ctx = Depends(_ctx)) -> dict:
    """Reset the caller's scope — the shared unit when signed in — and, when
    FHIR_WRITE is on, delete the baton-out-* chart outputs and reload."""
    st = store_mod.get_store()
    st.reset_state(ctx.scope)
    ctx.s.clear()
    ctx.s.update(state.fresh())  # so the request teardown persists fresh state
    _record(ctx, None, "Reset the demo", "reset")
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
