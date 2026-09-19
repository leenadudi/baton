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

Free-text notes go through an extraction step (OpenAI API) that returns the same `{role, topic, value}` tags a rule engine already uses to detect conflicts — the model reads, the rules decide, so every flag stays auditable back to a source note.

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
