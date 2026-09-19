# Baton — repo notes

Shift-handoff drafting from the chart. Flags conflicting instructions, incomplete
handoffs, and stuck administrative blockers. See `README.md` for the full pitch.

Global working rules live in `~/.claude/CLAUDE.md` — not repeated here.

## Stack

- `backend/` — FastAPI, Python 3.11+. Currently only `GET /api/health`.
- `frontend/` — React + Vite, JS (not TS). No test runner configured yet.
- `frontend/public/prototype.html` — standalone working UI, rule engine over
  hardcoded demo data. Reference implementation while porting to React; do not
  delete or refactor it as part of unrelated work.

## Run

```sh
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev     # http://localhost:5173
```

CORS in `backend/app/main.py` allows `http://localhost:5173` only — a frontend
port change needs that list updated too.

## Constraints that shape the code

- **FHIR-native, no custom data model.** Chart data maps to standard resources
  (`DocumentReference`, `MedicationRequest`, `AllergyIntolerance`, `CarePlan`,
  `CareTeam`, `ServiceRequest`, `Task`). Don't invent parallel schemas.
- **The model reads, the rules decide.** Free-text extraction (OpenAI API)
  returns `{role, topic, value}` tags; conflict detection is rule-engine logic
  over those tags. Every flag must trace back to a source note — no LLM call may
  be the thing that decides a flag.
- **Read-only against the chart.** No write-back. Baton generates a brief a
  clinician copies manually.
- **Surfaces, does not adjudicate.** For conflicts, show both snippets and
  authors; never pick a winner.
- Baton does not diagnose or recommend treatment.

## Workstreams

Tracked as GitHub issues at `leenadudi/baton`. Check the relevant issue before
starting work in an area — scope per workstream is defined there, and issue
alignment takes priority over drive-by improvements.
