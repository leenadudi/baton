# Baton

**HackMIT 2026 · Healthcare Track**

Every shift change risks losing critical information. Baton turns the patient’s chart into a ready-to-review handoff, automatically surfacing conflicting instructions, missing information, and stuck tasks before they become the next shift’s problem.

**Live demo:** [batoncom.vercel.app](https://batoncom.vercel.app)

## What it does

At shift change, a nurse or resident re-reads the whole chart to reconstruct what the last shift already knew. What actually gets lost isn't a diagnosis — it's coordination: contradictory orders from different roles, handoff fields nobody filled in, and administrative work that sat still while the clock ran. Baton reads a patient's real FHIR chart and surfaces exactly that, in one screen per unit:

- **Conflicting instructions** — different care team members left contradictory orders on the same topic (anticoagulation, weight-bearing, discharge destination, diet, fluids, isolation). Baton shows both source snippets and their authors side by side; it never picks a winner.
- **Incomplete handoffs** — required fields missing (code status, allergies, follow-up owner, medication reconciliation) and pending results nobody owns.
- **Stuck administrative blockers** — authorizations, referrals, or equipment requests that haven't moved, aged and severity-scored.
- **Completed** — a live history of every resolved action on a patient (cleared blocker, filled field, reconciled conflict), so nothing that's actually done still reads as open.
- **Patient info** — DOB, sex, active medications, active problems, latest vitals and labs, social history, recent procedures, past visits, and the care team roster, pulled straight from the chart so nobody needs a second system open.

Baton reads the chart; it does not diagnose or recommend treatment, and by default it never writes back to it. It generates a shift-handoff brief a clinician reviews and copies — that's the whole write path unless `FHIR_WRITE` is explicitly turned on (see below).

## Model reads, rules decide

This is the architectural rule the whole system is built around, and it's what makes every flag on screen auditable.

Free-text clinical notes go through an OpenAI (`gpt-4o-mini`) extraction step that returns structured `{role, topic, value}` tags — nothing more. A separate, deterministic Python rule engine, ported line-for-line from the original working prototype, is the *only* thing that decides what counts as a conflict, an incomplete field, or an aged blocker. The model never classifies an issue type and never picks a winning instruction. That separation means every flag traces back to one specific note or FHIR resource, never to a model's own judgment call.

## FHIR-native — no custom data model

| Data | FHIR resource |
|---|---|
| Notes (free text) | `DocumentReference` |
| Active medications | `MedicationRequest` |
| Active problems | `Condition` |
| Allergies | `AllergyIntolerance` |
| Code status | `Consent` |
| Vitals, labs, social history | `Observation` |
| Recent procedures | `Procedure` |
| Past visits | `Encounter` |
| Care team roster | `CareTeam` |
| Consults / referrals | `ServiceRequest` |
| Follow-up owner, admin blockers | `Task` |

Chart data is read from a public HAPI FHIR test server loaded with real Synthea-generated patients — not a mock dataset. Six demo personas are mapped onto real generated patients and carry hand-authored fixture notes/blockers/handoff fields layered on top (Synthea's own generated note text is thin and templated); everything else on this page — labs, vitals, medications, problems, procedures, visit history — is that patient's actual generated chart, read live.

## Architecture

```text
Public HAPI FHIR test server (Synthea data)
        │  FHIR reads, and optional writes if FHIR_WRITE=1
        ▼
FastAPI backend — FHIR client · OpenAI extraction · rule engine · panel + brief APIs
        │  JSON: patients, issues, patient info, brief text
        ▼
React + Vite frontend — falls back to a local rule engine over cached
data if the API is cold or unreachable, then upgrades once it answers
```

Deployed on **Render** (FastAPI) and **Vercel** (React SPA). Render's free tier sleeps after idle, so the frontend falls back to a local rule engine over cached data after a 6-second timeout and upgrades to live data once the backend answers — a cold start never means a blank screen for judges. A scheduled workflow pings the API periodically to reduce how often it goes cold.

## Team

| | |
|---|---|
| Sophie Cheung | Frontend & design |
| Leena Dudi | Backend, API, FHIR client, rule engine |
| Amy Lin | FHIR test data, demo fixtures |
| Nicole Zheng | OpenAI note extraction, evaluation |

## Project structure

```text
backend/                       FastAPI application — FHIR client, rule engine, extraction endpoint
frontend/                      React + Vite application
frontend/public/prototype.html Standalone working UI prototype (rule engine over hardcoded demo data) — reference while porting to React
scripts/                       Data loading, fixture generation, and extraction scoring
```

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

- `GET /patients`, `GET /patients/{id}` — unit panel: patient + handoff fields, notes, patient info, and current issues in one response
- `POST /patients/{id}/notes` — demo-only: add an instruction note locally (not a FHIR write)
- `PATCH /issues/{id}` — demo-only local state: owner, fill field, pending owner, clear/escalate blocker, adopt a conflict value
- `POST /extract` — free-text note → `["topic","value"]` tags (OpenAI; needs `OPENAI_API_KEY`)
- `GET /brief` — plain-text shift handoff, severity then soonest discharge, cap 14 + remainder line
- `POST /demo/reset` — clear in-memory demo state
- `GET /fhir/status` — FHIR base URL and server `fhirVersion`
- `GET /fhir/patients` — patients from `dataset/patient_ids.json` (or a `Patient` search if absent)
- `GET /fhir/patients/{id}/chart` — the full chart (Patient, DocumentReference, MedicationRequest, Task, etc.) with per-type counts

### Extraction evaluation

```sh
cd backend
set -a; source .env; set +a      # loads OPENAI_API_KEY from backend/.env
python3 ../scripts/score_extraction.py    # prototype notes: 16/16 exact match
```

A second, harder eval set (`eval/`, `scripts/score_hard_cases.py`) is in review on [#39](https://github.com/leenadudi/baton/pull/39).

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
