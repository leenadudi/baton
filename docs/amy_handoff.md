# Handoff: FHIR test data (Amy, issue #16)

Summary of what was done in PR #20 and what remains, so another person or agent can pick up the data workstream. Product spec is `docs/prd.md`; the PRD wins on product behavior.

## What PR #20 delivered

### Data pipeline (issue #16)
- `scripts/generate_synthea.sh <count>` — clones Synthea into `.synthea/` (gitignored), runs `./run_synthea -p <count> -s 42 Massachusetts`, copies the FHIR R4 bundles into `dataset/synthea/` (gitignored, regenerable).
- `scripts/load_fhir.py --bundles dataset/synthea --base-url <FHIR_BASE_URL>` — uploads bundles to a FHIR server and writes the server-assigned IDs to `dataset/patient_ids.json`.
  - Public HAPI rejects Synthea transaction bundles (HTTP 413 on multi-MB bundles; `HAPI-2282` on conditional `Practitioner?identifier=` references). The loader falls back to posting resources one at a time in dependency order, rewrites `urn:uuid` references to server IDs, and maps `412 duplicate` Medications to the existing resource. This is slow (~0.5 s/resource, ~1,300 resources/patient) and creates duplicates if rerun; acceptable for synthetic data.
- **7 Synthea patients are loaded on the public HAPI server** `https://hapi.fhir.org/baseR4`. IDs are committed in `dataset/patient_ids.json` (`Patient/42157`, `43825`, `44086`, `44970`, `46315`, `47767`, `48900`).
- Public HAPI is shared, unauthenticated, and wiped periodically. If charts start returning 404, rerun `generate_synthea.sh` + `load_fhir.py`. Local fallback: `docker run -d -p 8080:8080 hapiproject/hapi:latest` and `FHIR_BASE_URL=http://localhost:8080/fhir`.

### Resource coverage vs PRD §7 table
Present in the loaded Synthea data: `Patient`, `Encounter`, `Condition`, `Observation`, `DocumentReference`, `DiagnosticReport`, `MedicationRequest`, `AllergyIntolerance`, `CarePlan`, `CareTeam`, `Procedure`, `Immunization`.

**Missing (Synthea does not emit them):** `Task`, `Goal`, `Consent`, `ServiceRequest`, `PractitionerRole`. The "stuck blocker" and "follow-up owner" flags depend on `Task`, so these must be hand-authored.

`DocumentReference` note text is templated Synthea boilerplate — too thin for the conflict-extraction demo.

### Backend pieces that consume the data (issue #14, for context)
- `backend/app/fhir_client.py` — read-only `FhirClient` (`get`, `search` with paging, `patient_chart`). Default base URL is public HAPI; override with `FHIR_BASE_URL`.
- Routes: `GET /fhir/status`, `GET /fhir/patients` (reads `dataset/patient_ids.json`), `GET /fhir/patients/{id}/chart`.
- `backend/app/rules.py` — Python port of the prototype's `findConflicts`/`getIssues`; `backend/app/demo_patients.py` holds the six PRD §5 demo patients as the target data shape.
- `POST /extract` — OpenAI note → `["topic","value"]` tags, closed vocabulary in `rules.TOPICS`.

## Issue checklist state after PR #20

### #16 (Amy)
- [x] Install Synthea
- [x] Generate synthetic patients
- [x] Upload to public HAPI
- [x] Query data back out
- [x] Check every resource type in the §7 table (see coverage above)
- [x] Record exact patient IDs (`dataset/patient_ids.json`)
- [x] Review Synthea note quality (thin/templated)
- [ ] Swap in richer note text (MTSamples-style) with Nicole
- [ ] Map loaded patients onto the six PRD §5 demo patients
- [x] Hand FHIR URL + loaded contents to Leena

### #14 (Leena) — checked in PR #20
Setup, FHIR client, rule-engine port, CORS (`localhost:5173` + `CORS_ORIGINS`), requirements, `/extract` pair normalization. Still open: `GET /patients`, `GET /patients/:id`, `GET /brief`, demo-only `POST /patients/:id/notes` / `PATCH /issues/:id`, Render deploy.

## Remaining work for the data workstream (Amy)

Goal: the 2–3 demo patients on public HAPI carry the exact notes, handoff fields, and blockers from the six prototype personas, so Leena's `GET /patients` can read them from FHIR and the rule engine fires the same flags the prototype shows. Source of truth for every value below: `frontend/public/prototype.html` `PATIENTS` array (also copied verbatim in `backend/app/demo_patients.py`).

### Task 1 — Map personas to loaded patients
- Pick loaded patients for the personas. Minimum: **p1 Margaret A.** (hero case: 3 conflicts + 2 blockers + missing follow-up owner), **p2 Robert C.** (2 conflicts, missing code status, 2 blockers), **p6 David L.** (clean discharge — the "no flags" control). Ideally all six.
- Prefer loaded patients whose age/sex roughly match (Margaret 78F, Robert 64M, Priya 41F, James 55M, Elena 83F, David 29M). Names/rooms can be overridden in the API layer, so an exact match is not required.
- Deliverable: `dataset/demo_patients.json` — `{ "p1": {"fhirPatientId": "Patient/42157", "name": "Margaret A.", "room": "412", "dx": "...", "dischargeInH": 30}, ... }` for each mapped persona. Leena's `GET /patients` reads this to build the panel.

### Task 2 — Author `DocumentReference` notes (issue #16 "swap in richer note text")
For every note in each mapped persona's `notes` array, create one `DocumentReference`:
- `status: "current"`, `type`: LOINC `34109-9` (Note), `subject.reference: "Patient/<id>"`.
- `author[0].display` = prototype author (e.g. `"Dr. Reyes"`); role goes in `author[0].display` suffix or, preferably, in a `Practitioner`/`PractitionerRole` you also create (see Task 5). At minimum put the role in `category[0].text` (e.g. `"Orthopedics"`) so the backend can read it without resolving references.
- `date` = now minus the note's `h` hours (e.g. Margaret's Ortho note `h:40` → 40 hours ago). **Recency matters**: the rule engine picks the latest note per role and treats reconcile notes as a barrier — wrong ordering breaks the hero case.
- `content[0].attachment.contentType: "text/plain"`, `content[0].attachment.data` = base64 of the exact prototype `text`.
- Do **not** store the `tags` — those come from `POST /extract` at runtime (Nicole's pipeline).
- Note counts: p1 6, p2 3, p3 1, p4 1, p5 4, p6 1 (16 total).

### Task 3 — Author `Task` resources for blockers
For every entry in `blockers` (p1 2, p2 2, p4 2, p5 1 — p3/p6 none):
- `status: "requested"` (open), `intent: "order"`, `for.reference: "Patient/<id>"`.
- `description` = label (e.g. `"SNF insurance authorization"`); `code.text` = category (`Prior authorization`, `Transport`, `Equipment (DME)`, `Patient education`, `Referral`).
- `owner.display` = `waitingOn` (e.g. `"Payer"`, `"Case Management"`).
- `authoredOn` = now minus `ageH` hours (the engine computes "waited ≥24h" from this).
- Mark `blocks: true` via `priority: "urgent"` or a boolean extension — agree the encoding with Leena; document whichever you choose in this file.
- Also create one `Task` per `pending` result (p1 "Repeat hemoglobin"/"Type and screen", p4 "HbA1c", p5 "Sputum culture") with `code.text: "Pending result"` and `owner.display` = owner (empty owner → omit `owner`, which is what triggers the "pending result with no owner" flag).

### Task 4 — Encode handoff fields
Each persona's `handoff` object (`codeStatus`, `allergies`, `familyContact`, `followUpOwner`, `medRec`) must be readable from FHIR:
- `codeStatus` → `Consent` (scope `adr`) or `Goal` with `description.text` = `"Full code"` / `"DNR/DNI"`. **Leave it out for p2** (missing code status is a deliberate flag).
- `allergies` → `AllergyIntolerance` with `code.text` (`"Penicillin (rash)"`, `"Sulfa (hives)"`); `"NKDA"` → one `AllergyIntolerance` with `code.text: "No known drug allergies"`. **Omit for p5** (missing allergies is a deliberate flag). Synthea already loaded some `AllergyIntolerance`s on these patients — delete or ignore them so they don't contradict the persona.
- `familyContact` → `Patient.contact[0].name.text` + `relationship`. **Omit for p3.**
- `followUpOwner` → `Task` with `code.text: "Follow-up owner"`, `owner.display`. **Omit for p1.**
- `medRec` → `Task` with `code.text: "Medication reconciliation"`, `status: "completed"`. **Omit for p4.**

### Task 5 — Optional but nice: `PractitionerRole`, `CareTeam`, `ServiceRequest`
- One `Practitioner` + `PractitionerRole` per author/role pair, referenced from note `author`, so the role comes from the chart rather than a text field.
- A `CareTeam` per patient listing those roles.
- A `ServiceRequest` for consults implied by the notes (e.g. p5 Infectious Disease, p1 PT). These make every row of the PRD §7 table light up in the demo.

### Task 6 — Make it reloadable
- Save every hand-authored resource as JSON under `dataset/fixtures/<persona>/*.json` (use `urn:uuid` placeholders for the Patient reference, or a `{{PATIENT_ID}}` token).
- Write `scripts/load_fixtures.py --base-url <FHIR_BASE_URL> --demo dataset/demo_patients.json` that substitutes patient IDs and POSTs them (reuse the single-resource posting helpers in `scripts/load_fhir.py`). Idempotency: use `PUT` with `identifier`-based conditional update or a fixed `id` prefix (e.g. `baton-p1-note-1`) so reruns after a public-HAPI wipe don't duplicate.
- Add a "Reload demo fixtures" subsection to `README.md`.

### Task 7 — Verify and hand off
- `curl https://hapi.fhir.org/baseR4/DocumentReference?patient=<id>&_count=50` returns the persona's notes with correct `date` ordering; `Task?patient=<id>` returns the blockers.
- `GET /fhir/patients/{id}/chart` via the backend shows nonzero `DocumentReference`, `Task`, `AllergyIntolerance`, `Consent`/`Goal` counts for each mapped persona.
- Run `python scripts/score_extraction.py` — still 14/16 or better (confirms the note text is unchanged).
- Tick the remaining boxes on issue #16, and tell Leena the persona → `Patient/<id>` mapping and the `blocks`/role encodings chosen so `GET /patients` can rely on them.

### Definition of done
Leena can point `FHIR_BASE_URL` at public HAPI, call `GET /patients`, and see Margaret A. with `anticoagulation`, `weight_bearing`, and `destination` conflicts, two high-severity blockers, and a missing follow-up owner; Robert C. with `fluids`/`diet` conflicts and missing code status; David L. with no flags — all derived from FHIR resources, not from `demo_patients.py`.

### Constraints
- Synthetic data only on public HAPI (shared, unauthenticated, world-writable, wiped periodically).
- The Baton backend never writes to FHIR — all fixture loading happens via scripts.
- Keep the closed vocabulary: note text must map to the existing `TOPICS` values; don't invent new topics.
- No secrets in the repo; `OPENAI_API_KEY`/`FHIR_BASE_URL` stay in `backend/.env` (gitignored).
