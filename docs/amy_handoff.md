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

## What remains for the data workstream

1. **Pick 2–3 of the 7 loaded patients** to be the demo patients (PRD §5: Margaret A. = multi-conflict hero case, etc.). Record the mapping (demo persona → `Patient/<id>`) in `dataset/patient_ids.json` or a sibling file.
2. **Hand-author `DocumentReference` notes** on those patients using the exact prototype note text (`frontend/public/prototype.html`, `PATIENTS` array — also in `backend/app/demo_patients.py`). Each note needs author, role (Orthopedics, Hospitalist, Dietitian, Nursing, PT/OT, Case Management…), and a timestamp so the rule engine's recency logic works. `POST https://hapi.fhir.org/baseR4/DocumentReference` with `subject.reference = Patient/<id>`, `content[0].attachment.data` = base64 note text.
3. **Hand-author `Task` resources** for the blockers (auth, referral, DME, teaching, transport) with `status`, `authoredOn` (so "waited ≥24h" can be computed), `for.reference = Patient/<id>`, and an extension or `code` marking whether it blocks discharge.
4. Optionally add `Goal`/`Consent` for code status and `ServiceRequest` for consults, so the §7 table is fully exercised.
5. Put these fixtures in the repo (e.g. `dataset/fixtures/*.json`) with a small script to POST them, so the demo can be reloaded after a public HAPI wipe.

Constraints: synthetic data only on public HAPI; the backend never writes to FHIR — fixture loading is done by scripts, not the app.
