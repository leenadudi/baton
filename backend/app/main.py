import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / "backend" / ".env")

from app.extract import extract
from app.fhir_client import FhirClient

PATIENT_IDS_FILE = REPO_ROOT / "dataset" / "patient_ids.json"

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


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "message": "Baton API is running"}


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
