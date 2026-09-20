# Baton — Product Requirements Document

**Event:** HackMIT 2026, Healthcare Track
**Repo:** [leenadudi/baton](https://github.com/leenadudi/baton)
**Audience:** The four of us building this in ~24 hours. This document is the shared plan for the whole codebase. Work is split by GitHub issue; build your slice against this PRD, not against a private interpretation of the prototype.

| Person | GitHub | Owns | Start here |
|---|---|---|---|
| Sophie Cheung | `sophieluo08-boop` | Frontend & design | [#13](https://github.com/leenadudi/baton/issues/13) |
| Leena Dudi | `leenadudi` | Backend, API, FHIR client | [#14](https://github.com/leenadudi/baton/issues/14) |
| Nicole Zheng | `nmzheng` | OpenAI note extraction | [#15](https://github.com/leenadudi/baton/issues/15) |
| Amy Lin | `alsy7009` | FHIR test data | [#16](https://github.com/leenadudi/baton/issues/16) |

Issue tracker is the source of truth for checklists. This PRD is the source of truth for *what the product is*, *what each layer must produce*, and *how the layers fit together*.

---

## 1. Problem

At shift change, a nurse or resident has to re-read the chart to reconstruct what the last shift already knew. What actually drops is not a diagnosis — it is coordination: contradictory instructions from different roles, required handoff fields that were never filled, and administrative work (auth, referral, DME) that sat still while the clock ran.

Epic and Oracle Health already ship **handoff activity forms**. Those forms are empty. Clinicians retype into them. Baton's job is not to invent another form.

**Pitch line:** they give you the form; we fill it in and tell you what's missing.

---

## 2. What Baton is

Baton drafts the nursing/resident shift handoff from a patient's chart and flags what is missing, contradicted, or stuck — before the next shift has to catch it by re-reading everything.

It is a **coordination / operations** tool. That framing matches the healthcare track. It is also a hard product constraint:

- Baton **does not diagnose**.
- Baton **does not recommend treatment**.
- Baton **does not decide who is right** when instructions conflict. It shows both source snippets and authors.
- Baton **does not write back** to any FHIR server in this build.

If a feature would require clinical judgment or a signed note, it is out of scope.

---

## 3. Flag types (the product)

Every open item Baton shows is one of three types. The rule engine in `frontend/public/prototype.html` (`findConflicts`, `getIssues`) is the behavioral spec. Port it; do not reinvent it.

### 3.1 Conflicting instructions

Different care-team members left contradictory orders or notes on the **same topic**.

Topics and allowed values (from the prototype `TOPICS` object — extraction **must** emit these keys, not a new vocabulary):

| Topic key | Label | Allowed values | Default severity |
|---|---|---|---|
| `anticoagulation` | Anticoagulation | `continue`, `hold` | high |
| `weight_bearing` | Weight-bearing | `full`, `partial`, `non-weight-bearing` | high |
| `destination` | Discharge destination | `home`, `home with home health`, `SNF`, `inpatient rehab` | high |
| `diet` | Diet | `regular`, `cardiac 2g Na`, `carb-consistent`, `NPO`, `clear liquids` | med |
| `fluids` | Fluids | `restrict`, `encourage` | med |
| `isolation` | Isolation | `contact precautions`, `none` | med |

**Rule:** for each topic, take the latest instruction **per role**. If two or more roles currently disagree, flag it. A reconciling decision (prototype: adding a note with `reconcile: true`) raises a barrier so older instructions stop counting.

**UI contract:** show both source snippets, role, author, and recency. Offer "Use this" as a local reconciling action. Do not auto-pick a winner.

### 3.2 Incomplete handoffs

Required fields empty, plus pending results with no owner.

| Field key | Label | Severity | Why it matters |
|---|---|---|---|
| `codeStatus` | Code status | high | Oncoming staff cannot act safely in an emergency without it. |
| `allergies` | Allergies | high | Orders may be placed without allergy status. |
| `followUpOwner` | Post-discharge follow-up owner | med | Follow-up slips if nobody is named. |
| `medRec` | Medication reconciliation | med | Discharge meds not checked against home meds. |
| `familyContact` | Family or surrogate contact | low | No one to call if status changes or consent is needed. |

Unowned pending results (e.g. "Repeat hemoglobin", "Type and screen") are also incomplete-handoff flags, medium severity.

### 3.3 Stuck administrative blockers

Authorizations, referrals, equipment (DME), teaching, transport still open.

**Severity:**

- **High** if the item blocks discharge **and** (discharge is due within 24h **or** the item has waited ≥ 24h).
- **Low** if it does not block discharge **and** has waited < 24h.
- **Medium** otherwise.

Prototype actions: mark cleared, escalate. These are local demo actions, not FHIR writes.

### 3.4 Ownership is part of the product

Every issue can be assigned to a role. Unassigned issues are counted on the unit tiles because an issue nobody owns is how things get dropped. Owner options in the prototype: Charge RN, Hospitalist, Case Management, Pharmacy, Social Work, PT/OT, Unit Clerk.

---

## 4. Goals for the hackathon build

### Must ship (demo path)

1. **Panel-level unit view** for a med-surg unit ("4 West"): all demo patients + current flags in one screen. A nurse handing off six patients needs one screen, not six launches.
2. **Patient detail** with issue cards, filters, handoff checklist, notes with tags, owner assignment, shift-brief modal (generate + copy).
3. **Real FHIR reads** against a public HAPI FHIR test server loaded with Synthea (plus richer notes if Synthea text is too thin).
4. **OpenAI extraction:** free-text note → `{role, topic, value}` tags. Model reads; rules decide.
5. **Python rule engine** equivalent to `findConflicts` / `getIssues`, run over parsed FHIR + extracted tags.
6. **Generate-and-copy brief** with **zero write permissions** to FHIR.
7. **Shift-change trigger** as a timer (not a scheduling integration), named as a finding on the pitch.

### Explicit non-goals (cut before cutting the FHIR/extraction path)

- Mobile polish beyond a basic narrow-layout check.
- Live-wiring every generated patient. **2–3 demo patients** fully wired is enough; the rest can be seed / fallback.
- Any dataset that needs a data-use agreement (MIMIC-IV, n2c2). Approval will not clear in time. Use Synthea + MTSamples (Kaggle, free, CC0).
- Signed clinical-note write-back. Do not build it. Do not imply it is coming.
- Diagnosing, scoring acuity, or recommending treatment.
- A custom proprietary patient schema. Standard FHIR only.
- Dropbox-as-source-of-truth ([#5](https://github.com/leenadudi/baton/issues/5)). That was the pre-FHIR plan. Do not start it unless the FHIR demo already works end to end.
- Production Epic / Oracle Health access. Mention as the real-world path; do not chase tonight. `fhir.epic.com` and Oracle's developer program are free sandboxes, but production Epic needs a customer sponsor.

### Stretch (only after the demo path works)

- CDS Hooks `patient-view` cards when a chart opens ([#8](https://github.com/leenadudi/baton/issues/8)).
- SMART on FHIR embedded launch via [launch.smarthealthit.org](https://launch.smarthealthit.org) (no approval).
- One narrowly scoped Devin task ([#6](https://github.com/leenadudi/baton/issues/6)) — e.g. FHIR client wiring **or** `prototype.html` → React split. A working demo without Devin beats a broken one with it.
- Dropbox citation links / folder briefs ([#5](https://github.com/leenadudi/baton/issues/5)) as a sponsor-challenge extra.

---

## 5. Users and demo moment

**Primary user:** bedside nurse or night/day resident at shift change on a medical-surgical unit.

**Secondary users in the story:** charge RN, case management, pharmacy — they appear as owners, not as separate apps.

**Demo script (keep this runnable):**

1. Open the unit panel. Summary tiles show conflicts, handoff gaps, blockers, unowned issues, and discharges due in 24h that are at risk.
2. Select **Margaret A.** (hip fracture): anticoagulation continue vs hold, weight-bearing partial vs full, destination SNF vs home, missing follow-up owner, stuck SNF auth + transport.
3. Open a conflict card. Show both snippets. Do **not** auto-resolve.
4. Open **Shift brief**. Copy text. Emphasize: generated, clinician-reviewed, not written to the chart.
5. Optionally: fire the shift-change timer; explain that FHIR has no "shift change" event.

Prototype patients to preserve as the narrative set (map onto Synthea IDs when data is loaded):

| Demo id | Patient | Why they exist |
|---|---|---|
| `p1` | Margaret A., 78, Rm 412 | Multi-conflict + blockers. Hero case. |
| `p2` | Robert C., 64, Rm 407 | Fluids/diet conflict + DME/teaching blockers + missing code status. |
| `p3` | Priya S., 41, Rm 305 | Mostly clean; missing family contact. Contrast case. |
| `p4` | James O., 55, Rm 418 | Missing med rec, unowned pending result, auth + teaching. |
| `p5` | Elena V., 83, Rm 421 | Isolation + destination conflict, missing allergies, referral stuck. |
| `p6` | David L., 29, Rm 310 | Clean discharge. Interactive "add NPO as Dietitian" conflict demo. |

---

## 6. Architecture

```text
┌─────────────────┐     GET FHIR resources      ┌──────────────────────────┐
│  HAPI FHIR      │◄────────────────────────────│  FastAPI backend         │
│  public test    │                             │  - FHIR client (read)    │
│  server         │                             │  - POST /extract (Nicole)│
│  (Amy loads)    │                             │  - rule engine (Leena)   │
└─────────────────┘                             │  - panel + brief APIs    │
                                                └────────────┬─────────────┘
                                                             │ JSON patients + issues
                                                             ▼
                                                ┌──────────────────────────┐
                                                │  React + Vite (Sophie)   │
                                                │  port of prototype.html  │
                                                └──────────────────────────┘
```

**Stack (already in repo):**

- Frontend: **React + Vite** (`frontend/`). Keep Vite. React is the UI library; Vite is only the bundler/dev server. You cannot ship "just React" without *some* bundler (CRA/`react-scripts` is the same class of tool and still inlines `REACT_APP_*` into the browser). Switching to Next.js would rewrite Sophie's slice for no product gain. Starter is empty except a health-check ping.
- Backend: FastAPI (`backend/app/main.py`). Today: `/api/health` + CORS for `http://localhost:5173`.
- Reference UI + rule engine: `frontend/public/prototype.html`. Treat this as the spec for frontend *and* backend behavior, not a throwaway mockup.
- **Do not use Firebase** (including Blaze). We do not need auth, realtime DB, or hosting from Google for this demo.

**Vite does not leak keys by existing.** Keys leak if you put them in any `VITE_*` (or `REACT_APP_*`) env var — Vite inlines those into the public JS bundle. Fix:

- `OPENAI_API_KEY` and the FHIR client live **only** on FastAPI (`os.environ`, Render env, never `VITE_`).
- The only frontend env var allowed is `VITE_API_URL` (public backend URL, not a secret).
- Extraction (`POST /extract`) never runs in the browser.

**Hosted demo (judges, not localhost):** Vercel Hobby for the Vite SPA + **Render Free** Web Service for FastAPI. Public HAPI FHIR stays as-is. Details in §6.1.

**Separation that must survive the demo (OpenAI Challenge):**

1. Model (OpenAI) **extracts** `{role, topic, value}` from note text.
2. Untouched **rule engine** decides conflicts, incomplete fields, and aged blockers.
3. Every flag is auditable to a source note (and, when we have it, a FHIR resource id).

Do not let the model output "this is a conflict." That decision stays in code.

**Write-back:** generate-and-copy only. The generate-brief endpoint returns text. It never `POST`s/`PUT`s to FHIR. Next rung *if ever* (pitch only): write a `Task` — the resource EHRs most readily accept writes on. Signed notes are out.

### 6.1 Public hosting (judges must get the full UX)

Localhost is for development only. Judges need one public URL that does list → patient → flags → extract-backed tags → copyable brief.

| Piece | Host (free) | Why |
|---|---|---|
| React SPA | **Vercel** Hobby | Native Vite static deploy. `VITE_API_URL` = Render origin. |
| FastAPI | **Render** Free Web Service | Runs Python as-is (FHIR reads + OpenAI). Vercel is a poor fit for long-lived FastAPI + outbound FHIR/OpenAI. |
| Chart data | Public **HAPI FHIR** test server | Already free; Amy loads Synthea here. |
| Secrets | Render env vars | `OPENAI_API_KEY`, `FHIR_BASE_URL`. Not on Vercel. |

**CORS:** allow `http://localhost:5173` **and** the Vercel production origin (and the `*.vercel.app` preview origin if we share preview links).

**Render free sleeps after idle.** Before a judging slot, open `https://<api>.onrender.com/api/health` once and wait for 200. Optional: a free UptimeRobot ping every 5 min so the API is warm. If Render is blocked, fallback is **Fly.io** free allowance — same split, still no Firebase.

**Sophie:** `vercel` from `frontend/` (or GitHub integration, root directory `frontend`, build `npm run build`, output `dist`). **Leena:** `backend/` as a Render Web Service, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

**Cost / token budget:** we have ~$25 in credits and a free Cursor plan. Cache extraction for the 2–3 demo patients (do not re-call OpenAI on every panel refresh). Keep Cursor/agent sessions scoped to one workstream. No paid Firebase, no Vercel Pro, no Render paid unless the free instance will not stay up for judging.

---

## 7. FHIR data model (no custom schema)

This is a positioning choice, not just an implementation detail. Epic/Oracle already have the form; Baton only holds up if it reads the same chart shape hospitals already use.

| Product data | FHIR resource | Used for |
|---|---|---|
| Notes (free text) | `DocumentReference`, `DiagnosticReport` | Extraction input |
| Meds | `MedicationRequest` | Chart context; anticoagulation orders |
| Allergies | `AllergyIntolerance` | Handoff field `allergies` |
| Code status / goals | `CarePlan`, `Goal`, `Consent` | Handoff field `codeStatus` |
| Care team | `CareTeam`, `PractitionerRole` | Role/author on notes and flags |
| Consults / referrals | `ServiceRequest` | Blockers / consults |
| Follow-up owner, admin blockers | `Task` | Owner, `status`, `businessStatus`, timestamps. "Unassigned follow-up" and "stuck 4 days" are queries, not bespoke logic. |

There is **no** FHIR event for "shift change." Timing lives in Amion, QGenda, UKG/Kronos, Microsoft Teams Shifts. Demo uses a timer. Pitch names Teams Shifts / Graph API as the production path. Frame this as a finding, not a gap we forgot.

Sandbox for tonight: **public HAPI FHIR test server** loaded with Synthea. SMART sandbox at launch.smarthealthit.org is the stretch launch path.

---

## 8. API contract

Lock this before splitting implementation. FHIR resource shapes are the chart; **this** is what React renders against.

### 8.1 Routes

| Method | Path | Owner | Purpose |
|---|---|---|---|
| `GET` | `/api/health` | already exists | Liveness |
| `GET` | `/patients` | Leena | Panel: every unit patient + current flags in **one** response |
| `GET` | `/patients/:id` | Leena | One patient: chart summary, notes, tags, issues, handoff fields |
| `POST` | `/patients/:id/notes` | Leena | Demo-only: add an instruction locally (David L. NPO trick). **Not** a FHIR write. |
| `PATCH` | `/issues/:id` | Leena | Demo-only local state: owner, fill field, clear/escalate blocker, adopt a conflict value |
| `POST` | `/extract` | Nicole (logic) / Leena (route) | Note text in → tags out |
| `GET` | `/brief` | Leena | Unit-wide shift-handoff text (all patients, severity then soonest discharge, cap 14 + remainder line); never writes FHIR |

CORS must allow `http://localhost:5173` and the deployed Vercel origin(s).

Demo mutations (`POST /patients/:id/notes`, `PATCH /issues/:id`) may live in memory only — Render cold starts reset them. That is acceptable: re-do the demo action after a wake rather than persisting demo state. Demo state is scoped per `X-Session-Id` (the frontend mints one per browser into localStorage), so each judge gets an independent sandbox; requests without the header share a default session.

### 8.2 `POST /extract`

**Request:**

```json
{
  "text": "Partial weight-bearing on the operative leg for 6 weeks.",
  "author": "Dr. Reyes",
  "role": "Orthopedics"
}
```

`role` may be omitted if the model should infer it; prefer passing role when FHIR already has it.

**Response:** zero or more tags. Same schema the rule engine already consumes.

```json
{
  "role": "Orthopedics",
  "tags": [
    { "topic": "weight_bearing", "value": "partial" }
  ]
}
```

Topics and values **must** be from the `TOPICS` table in §3.1. If the note has no matching instruction, return `"tags": []`. Do not invent topics.

`/extract` returns `{topic, value}` objects because that is the friendliest model schema, but the route **normalizes** each tag to the `["topic", "value"]` pair the prototype engine and `notes[].tags` consume before storing or returning it.

### 8.3 Panel patient object (frontend contract)

Shape the JSON so Sophie can swap mock `PATIENTS` for `GET /patients` without rewriting cards. Align with the prototype:

```json
{
  "id": "p1",
  "fhirPatientId": "Patient/123",
  "name": "Margaret A.",
  "age": 78,
  "room": "412",
  "dx": "Hip fracture, ORIF post-op day 2",
  "dischargeInH": 30,
  "handoff": {
    "codeStatus": "Full code",
    "allergies": "Penicillin (rash)",
    "familyContact": "Daughter, on file",
    "followUpOwner": "",
    "medRec": "Done by pharmacy"
  },
  "pending": [{ "name": "Repeat hemoglobin", "owner": "Night Resident" }],
  "blockers": [{
    "id": "b1",
    "label": "SNF insurance authorization",
    "cat": "Prior authorization",
    "waitingOn": "Payer",
    "ageH": 31,
    "blocks": true,
    "fhirTaskId": "Task/..."
  }],
  "notes": [{
    "role": "Orthopedics",
    "author": "Dr. Reyes",
    "h": 40,
    "text": "Partial weight-bearing on the operative leg for 6 weeks. Toe-touch, up to 50%.",
    "tags": [["weight_bearing", "partial"]],
    "source": { "resourceType": "DocumentReference", "id": "..." }
  }],
  "issues": []
}
```

Note `notes[].tags` uses `["topic", "value"]` pairs — the exact shape `tagOf` / `findConflicts` consume in the prototype. The backend emits pairs here even though `/extract` speaks in `{topic, value}` objects.

`issues` may be computed server-side (preferred, so React and brief share one engine) using the prototype issue shape: `id`, `pid`, `type` (`conflict` | `handoff` | `blocker`), `sev` (`high` | `med` | `low`), `title`, `sub`, `why`, plus type-specific fields (`topic`/`vals`, `fix`, `bid`).

Issue ids in the prototype look like `p1:conflict:anticoagulation`. Keep that pattern so owner maps and `PATCH` stay stable.

---

## 9. Workstreams (build off this)

Dependencies: Amy's server URL unblocks Leena's FHIR client. Nicole's extract function unblocks `POST /extract`. Sophie is **not** blocked — she builds on prototype mock data first.

```text
Amy (#16)  →  HAPI URL + 2–3 wired patients
                 ↓
Leena (#14) →  FHIR client + panel API + Python rules + brief + CORS
                 ↑
Nicole (#15) → extract(text) → POST /extract
                 ↓
Sophie (#13) → React UI on mocks → swap fetch() when /patients exists
```

### 9.1 Sophie — frontend (#13, detail in #2, pitch #12)

**Now:**

1. Node 20+, `cd frontend && npm install && npm run dev`.
2. Click through `http://localhost:5173/prototype.html` until the three flag types, filters, owners, checklist, and brief are muscle memory.

**Build:**

1. React Router: patient list page + patient detail page (panel can stay one layout with a selected patient, matching the prototype grid).
2. Components: `PatientList`, `PatientDetail`, `IssueCard`, `SummaryTiles`.
3. Copy the prototype `<style>` into the React app. Reuse; do not restyle from scratch unless there is leftover time.
4. Copy the `PATIENTS` array into a local JS module. Render from mocks until Leena's `/docs` is live.
5. Rebuild interactions: filter chips, owner dropdown, shift-brief modal (copy to clipboard), handoff checklist, adopt/fill/clear/escalate, add-note demo control.
6. Swap mocks for `fetch('http://localhost:8000/patients')` (or `VITE_API_URL`).

**If time:** loading/empty states, narrow layout, keep `:focus-visible`. Help the pitch slide in #12.

**Do not:** wait on backend to start; rewrite the visual language; add clinical-recommendation UI.

### 9.2 Leena — backend (#14, detail in #1, #4, #8, #10, #11)

**Now:**

1. Python 3.11+, venv, `uvicorn app.main:app --reload --port 8000`, confirm `/docs`.
2. 5–10 min team lock on §8 (patient/issue shapes, routes, extract contract).

**Build:**

1. FHIR client: HTTP GET only against Amy's HAPI URL for every resource in §7.
2. `GET /patients` — unit panel, flags included.
3. Port `findConflicts` / `getIssues` / blocker aging / handoff completeness to Python. Input is parsed FHIR + extracted tags, not the hardcoded JS array — behavior must still match the prototype on the six demo patients.
4. Generate-brief endpoint: text only, no FHIR write path. Verify there is no write client.
5. CORS for Vite.
6. Shift-change: button or timer that regenerates the brief / refreshes flags. Fine if it is fake.
7. pytest on endpoints once they exist.

**Stretch:** CDS Hooks `patient-view` first; SMART launch if time.

**Do not:** request FHIR write scopes; block on Devin; invent a second issue schema Sophie cannot consume.

### 9.3 Nicole — extraction (#15, detail in #3)

**Now:**

1. OpenAI API key (ask organizers / booth for credits first).
2. Treat prototype `TOPICS` as the closed schema.

**Build:**

1. MTSamples (~15–20 notes covering diet, anticoagulation, weight-bearing, isolation, destination, fluids). If Amy's Synthea notes are thin, backfill `DocumentReference.content` with this language.
2. Prompt: note text + topic list → JSON tags. Iterate in ChatGPT/Codex; that iteration is the OpenAI Challenge "Codex improved development" story. Runtime still calls the API from Python.
3. Ground truth: run extraction on the six prototype patients' note strings; score against the hand-written tags. Write the number down (e.g. 11/14). That number is a demo talking point.
4. Hand Leena a function `extract(text, role=None) -> tags`. She wraps `POST /extract`. You own what happens inside.

**Do not:** let the model classify issue type or pick a winning instruction; add topics that are not in `TOPICS`.

### 9.4 Amy — FHIR test data (#16, detail in #7, #9)

**Now:** FHIR is typed resources, not one blob. Baton reads those types so we do not invent a schema (#12).

**Build:**

1. Keep §7 visible (this PRD is that shared table).
2. Install Synthea; generate a few dozen synthetic patients.
3. Upload bundles to the **public HAPI FHIR test server** (no account).
4. Confirm queryability for every row in §7 (`DocumentReference`, `DiagnosticReport`, `MedicationRequest`, `AllergyIntolerance`, `CarePlan`, `Goal`, `Consent`, `CareTeam`, `PractitionerRole`, `ServiceRequest`, `Task`).
5. Inspect note text. If templated, work with Nicole to put MTSamples narrative on the 2–3 demo patients.
6. Hand Leena the base URL plus which patient IDs are the wired demo set (map to Margaret / Robert / … if possible).

**Do not:** wait on MIMIC; try to load the entire Synthea world into the UI.

---

## 10. Rule engine — porting notes

Canonical implementation: `findConflicts` and `getIssues` in `frontend/public/prototype.html`.

When porting to Python:

- Latest instruction per **role** per topic, after the latest `reconcile` barrier.
- Conflict iff more than one distinct `value` remains.
- Missing handoff field iff empty string / missing after applying local `filled` state.
- Pending result without owner → handoff issue.
- Blocker skipped if locally `cleared`.
- Sort issues by severity weight: high=3, med=2, low=1.
- Unit tiles: counts of conflict / handoff / blocker, count of issues with no owner, count of patients with `dischargeInH <= 24` and any high-severity issue ("at risk").
- Brief: all issues across the unit, severity then soonest discharge, cap list (prototype: 14) with a remainder line. Include UNASSIGNED owners.

Frontend may keep a JS copy for mock mode, but once `GET /patients` returns `issues`, prefer the server as the single engine so the brief and the cards cannot drift.

---

## 11. Current repo state

What is already true (do not redo):

- README describes the product and how to run both apps.
- FastAPI health endpoint + CORS.
- React starter pings `/api/health`.
- Full interactive prototype at `frontend/public/prototype.html` with six patients and the real rule engine.

What is not true yet:

- No React patient UI.
- No FHIR client.
- No extraction.
- No HAPI data load.
- No brief endpoint.
- `react-router-dom` is not in `frontend/package.json` yet (Sophie adds it).
- Backend `requirements.txt` is FastAPI + uvicorn only (Leena adds httpx/fhir client, OpenAI SDK as needed, pytest).

---

## 12. Constraints and safety

- **24-hour hackathon.** Sequence: mocks + rules + 2–3 FHIR patients + extract on those notes + copyable brief. Everything else is optional.
- **Synthetic data, no PHI.** UI should keep the prototype's "Synthetic data, no PHI" affordance.
- **Liability posture:** coordination aid; does not replace clinical judgment or hospital policy. Keep that footer.
- **Auditability:** flags cite source snippet + author + (when available) FHIR id.
- **Secrets:** `OPENAI_API_KEY` only on the FastAPI host (local `.env` gitignored; Render dashboard in prod). Never `VITE_OPENAI_*`, never commit `.env`, never call OpenAI from React.
- **Credits:** cache demo-patient extraction; prefer server rule engine over extra model calls.

---

## 13. Pitch (do not skip in the last hour)

Owner: whoever is on the deck; Sophie helps with positioning (per #13 — #12 is closed reference material). Content everyone should be able to say:

1. **Positioning:** Epic/Oracle already ship empty handoff forms. Baton fills the form and flags what is missing. We are not replacing the handoff tool.
2. **FHIR-native:** no custom data model; reads resources hospitals already have.
3. **Model vs rules:** OpenAI extracts tags; deterministic rules flag. Every flag traces to a note. (OpenAI Challenge.)
4. **Shift timing finding:** there is no FHIR resource for "Nurse A is leaving." That is why handoffs stay unautomated. Demo timer; production path is Teams Shifts.
5. **Write-back:** generate-and-copy. Zero write permissions. Next rung would be `Task`, not a signed note.

---

## 14. Definition of done (team)

The demo is done when all of the following are true:

- [ ] Unit panel shows 2–6 patients with the three flag types, sourced from FHIR for at least 2–3 of them (mocks acceptable as fallback if live HAPI blips).
- [ ] A conflict card shows two authors and snippets; Baton does not pick a winner.
- [ ] Extraction ran on real note text; we can quote an accuracy number vs prototype tags.
- [ ] Shift brief generates, copies, and is not written to FHIR (no write client in the backend).
- [ ] Shift-change timer exists and the deck explains why.
- [ ] README still runs: backend `:8000`, frontend `:5173`, prototype still at `/prototype.html`.
- [ ] Public Vercel URL + live Render API: judges can complete the unit panel → conflict card → copy brief path without localhost. Health check has been warmed if Render was asleep.

Individual checklists stay on #13–#16. If this PRD and an issue disagree on a *task checkbox*, follow the issue. If they disagree on *product behavior*, follow this PRD and update the issue.
