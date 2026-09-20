# Baton

Baton drafts the nursing/resident shift handoff from the chart and flags what's missing, contradicted, or stuck — so a nurse or resident isn't re-reading a full chart to catch what the last shift already knew.

Three flag types:

- **Conflicting instructions** — different care team members left contradictory orders/notes on the same topic (e.g. diet, anticoagulation, weight-bearing). Baton surfaces both source snippets and authors; it does not decide who's right.
- **Incomplete handoffs** — required fields missing (code status, allergies, follow-up owner, medication reconciliation).
- **Stuck administrative blockers** — authorizations, referrals, or equipment requests that haven't moved.

Baton reads the chart; it does not diagnose or recommend treatment.

## How it reads the chart

Standard FHIR resources — no custom data model:

| Data | FHIR resource |
|---|---|
| Notes (free text) | `DocumentReference`, `DiagnosticReport` |
| Meds | `MedicationRequest` |
| Allergies | `AllergyIntolerance` |
| Code status / goals | `CarePlan`, `Goal`, `Consent` |
| Care team membership | `CareTeam`, `PractitionerRole` |
| Consults / referrals | `ServiceRequest` |
| Follow-up owner, admin blockers | `Task` |

Free-text notes go through an extraction step (OpenAI API) that returns the same `{role, topic, value}` tags a rule engine already uses to detect conflicts — the model reads, the rules decide, so every flag stays auditable back to a source note. Scored against the six prototype patients' hand-written tags: 16/16 notes exact match, precision/recall 1.00 (`scripts/score_extraction.py`).

Write-back is deliberately minimal: Baton generates the handoff brief, a clinician reviews and copies it. No write permissions back to the chart.

## Project structure

```text
backend/                       FastAPI application — FHIR client, rule engine, extraction endpoint
frontend/                      React + Vite application
frontend/public/prototype.html Standalone working UI prototype (rule engine over hardcoded demo data) — reference while porting to React
```

## Prerequisites

- Node.js 20 or newer
- Python 3.11 or newer

## Run locally

Open two terminals from the repository root.

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

```sh
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (normally http://localhost:5173). The UI calls the API at http://localhost:8000; interactive API documentation is available at http://localhost:8000/docs. The standalone prototype is served at http://localhost:5173/prototype.html.

## FHIR data

Baton reads from any FHIR R4 server, selected with `FHIR_BASE_URL` (default: the public HAPI server `https://hapi.fhir.org/baseR4`).

Generate synthetic charts with Synthea (cloned into `.synthea/` on first run; requires Java 17):

```sh
scripts/generate_synthea.sh 20        # argument = patient count; output in dataset/synthea/
```

Load the bundles into the server and record the server-assigned patient ids:

```sh
python scripts/load_fhir.py --bundles dataset/synthea \
    --base-url https://hapi.fhir.org/baseR4
# writes dataset/patient_ids.json; --base-url defaults to $FHIR_BASE_URL,
# then to public HAPI
```

Then start the backend (defaults to public HAPI, or set `FHIR_BASE_URL` explicitly). The panel routes (`/patients`, `/brief`, notes/issues) read the demo fixture resources on the FHIR server by default, cached for 5 minutes; set `PANEL_SOURCE=demo` to force the hardcoded demo patients, and `POST /demo/refresh` to reload from FHIR on demand.

Optional write-back is off by default; set `FHIR_WRITE=1` to let Baton append its own `baton-out-*` resources (published briefs, reconciliations, owner/fill records — never touching fixture or patient data). With it enabled, `POST /brief/publish` writes the brief as a `Composition`, panel mutations record output resources, and `POST /demo/reset` deletes them. API routes:

- `GET /patients`, `GET /patients/{id}` — unit panel: patient + handoff fields, notes, and current issues in one response
- `POST /patients/{id}/notes` — demo-only: add an instruction note locally (not a FHIR write)
- `PATCH /issues/{id}` — demo-only local state: owner, fill field, pending owner, clear/escalate blocker, adopt a conflict value
- `POST /extract` — free-text note → `["topic","value"]` tags (OpenAI; needs `OPENAI_API_KEY`)
- `GET /brief` — plain-text shift handoff, severity then soonest discharge, cap 14 + remainder line
- `POST /demo/reset` — clear in-memory demo state
- `GET /fhir/status` — FHIR base URL and server `fhirVersion`
- `GET /fhir/patients` — patients from `dataset/patient_ids.json` (or a `Patient` search if absent)
- `GET /fhir/patients/{id}/chart` — the full chart (Patient, DocumentReference, MedicationRequest, Task, etc.) with per-type counts

### Demo fixtures

The six PRD personas (Margaret A., Robert C., …) are loaded onto the mapped
patients in `dataset/demo_patients.json` — notes as `DocumentReference`,
blockers/pending/owners as `Task`, code status as `Consent`, allergies as
`AllergyIntolerance`, family contact on `Patient.contact`. Persona content is
generated from `backend/app/demo_patients.py`, so fixtures and the mock data
can never drift.

Every Baton-authored resource carries `meta.tag` `{system:
"https://github.com/leenadudi/baton", code: "demo-fixture"}` — readers should
filter on it (or the `baton-` id prefix) since public HAPI refuses to delete
referenced Synthea resources.

Reload after a public-HAPI wipe (idempotent — fixed `baton-*` ids via PUT):

```sh
python scripts/load_fixtures.py --base-url https://hapi.fhir.org/baseR4
# or just regenerate the JSON under dataset/fixtures/ without a server:
python scripts/load_fixtures.py --dump-only
```
### Deploy (Render)

`render.yaml` defines a single `baton-api` web service (Python, `rootDir: backend`, `uvicorn app.main:app --port $PORT`). Set `OPENAI_API_KEY`, `FHIR_BASE_URL`, and `CORS_ORIGINS` in the Render dashboard; CORS always includes `http://localhost:5173`.

To use a local server instead of public HAPI, run HAPI in docker and point `FHIR_BASE_URL` (and `--base-url`) at it:

```sh
docker run -d --name hapi -p 8080:8080 hapiproject/hapi:latest
# wait until curl http://localhost:8080/fhir/metadata returns 200 (~1-2 min)
export FHIR_BASE_URL=http://localhost:8080/fhir
```
