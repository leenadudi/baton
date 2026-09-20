# Context: Baton note-extraction slice (Nicole)

## Project
Baton is a HackMIT 2026 (healthcare track, 24h) team project, repo `leenadudi/baton`. It is a care-team **coordination** tool, not a diagnostic one. It flags conflicting instructions, incomplete handoffs, and stuck administrative blockers for patients on a hospital unit. Product spec: `docs/prd.md` (the PRD wins on product behavior). Reference UI and rule logic: `frontend/public/prototype.html`.

Team split: Sophie (frontend), Leena (backend, API, FHIR client, `POST /extract` route), Nicole (OpenAI extraction, this slice), Amy (FHIR test data and fixtures).

## Nicole's slice
Turn a free-text clinical note into structured tags, using the OpenAI API called from Python on the backend. Measure how accurate it is.

**Hard rules**
- The model only extracts `{topic, value}` tags. It must NOT decide what counts as a conflict, classify issue types, or pick a winning instruction. The rule engine (`backend/app/rules.py`) decides.
- Topics and values are a closed vocabulary from `TOPICS` in `rules.py` (mirrors the prototype): `anticoagulation` (continue, hold), `weight_bearing` (full, partial, non-weight-bearing), `destination` (home, home with home health, SNF, inpatient rehab), `diet` (regular, cardiac 2g Na, carb-consistent, NPO, clear liquids), `fluids` (restrict, encourage), `isolation` (contact precautions, none). Never add topics or values.
- `OPENAI_API_KEY` lives only in `backend/.env` (gitignored) or Render env vars. Never commit it, never put it in `.env.example`, never use a `VITE_` variable.
- Demo data is synthetic. No real patient data.

## Current state (branch `nicole/extraction`)
- `backend/app/extract.py`: `async extract(text, role=None) -> {"role", "tags": [{"topic","value"}], "reconcile": bool}`. Uses `gpt-4o-mini` by default (override with `OPENAI_MODEL`), temperature 0, JSON mode, filters tags against `TOPICS`, at most one tag per topic, in-memory cache only.
- `backend/app/extract_prompt.py`: system prompt.
- `scripts/score_extraction.py`: scores `extract()` against the hand-written tags in `backend/app/demo_patients.py`. Run from `backend/`.
- Leena wraps `extract()` in `POST /extract` (request: `text`, `author`, `role`; response: `role`, `tags`). She normalizes tags to `["topic","value"]` pairs.

**Scores (prototype notes, 16 notes)**
- v1 (original prompt): 14/16 exact, precision 0.94, recall 0.94.
- v2 (added rule: only tag `destination` when a place is named): 15/16 exact, precision 1.00, recall 0.94.
- v3 (reworded Margaret's nursing-note fixture; no prompt change): 16/16 exact, precision 1.00, recall 1.00.

**Resolved:** Margaret A.'s nursing note read "Daughter says the family expects her to come home Friday.", hand-tagged `destination: home`; the model correctly emitted no tags (a family expectation is not an order — this was a fixture/labeling problem, not a prompt bug). Reworded in `backend/app/demo_patients.py` to "Discharge plan on care board: home Friday with daughter. Home health not yet arranged." (the "home Friday with daughter" wording alone was ambiguous and the model tagged `home with home health`; the added sentence disambiguates).

**Not yet synced (needs Amy):** `backend/app/demo_patients.py` is the documented single source of truth for fixtures (`scripts/load_fixtures.py` docstring) — `dataset/fixtures/*.json` is generated from it, never hand-edited, and the same note text is already live on the public HAPI FHIR server via PR #23. `fhir_panel.py`'s ground-truth lookup keys off exact note text, so until fixtures are regenerated (`python scripts/load_fixtures.py --dump-only`, or against `--base-url` to push live) the live/hosted pipeline still serves the old wording and would still call OpenAI live on it, correctly emitting no destination tag — reproducing the original miss. Regenerating locally only touches the `date` field on 62 other fixture files (timestamp churn, not content) alongside the real note-6 fix, so hold that regen until Amy/Leena are ready to push it to the shared FHIR server. `frontend/public/prototype.html` and `frontend/src/data/chart.js` also still carry the old wording (not edited here — prototype.html is explicitly protected in CLAUDE.md; both are Sophie/Amy's files).

## Remaining tasks (in priority order)
1. **Try/except around the OpenAI call** in `extract.py` so a failed or timed-out request returns `{"role": role, "tags": []}` instead of crashing the demo.
2. **Persistent cache for demo patients.** Render free tier restarts and loses in-memory state. Pre-compute extraction for the wired demo patients' notes, commit the result as a JSON file, load it at startup, and only call OpenAI on a cache miss.
3. **Second eval set (hard cases).** `eval/mtsamples_candidates.json` holds 19 excerpts from the MTSamples dataset (CC0), chosen by keyword filtering plus hand selection, including deliberate traps (patient wish, past-tense event, blank isolation placeholder, "continue IV fluids" which has no Baton value, generic advice). `role` and `expected` are blank on purpose: Nicole labels them by hand BEFORE running the model. Write a scorer for it that reports correct, missed, and invented tags separately from the prototype set. Add about 8 synthetic edge cases for gaps MTSamples lacks (isolation "precautions lifted" -> none, fluid restriction, "hold enoxaparin until repeat Hgb", "family hopes to go home", "medically ready for discharge, awaiting transport" -> no destination tag).
4. ~~Ask Leena whether `rules.py` uses the `reconcile` field the model returns.~~ Checked directly: `rules.py`'s barrier logic reads `note["reconcile"]`, but that's only ever set by an explicit user/API action (frontend "adopt" action, `main.py`'s `body.reconcile` on `POST /patients/:id/notes`) — never from `extract()`'s output. Both call sites of `extract()` (`main.py:90`, `main.py:148`) only use `result["tags"]`. Removed `reconcile` from `extract_prompt.py` and `extract.py`'s return value.
5. **Open a PR** from `nicole/extraction` and mention Leena. Check PR #20 (Devin) for overlap before changing interfaces.

## Open labeling decisions (write the chosen rule into the prompt)
- Does "weightbearing as tolerated" map to `full`, or get no tag?
- Does "nursing home" map to `SNF`?
- Past-tense hospital-course statements ("diet was advanced") are not active instructions (current stance).
- Patient or family wishes are not instructions (current stance).

## Cautions
- Report accuracy as separate numbers (prototype notes, hard/edge cases, MTSamples), not one blended total. The prototype notes and tags were written together, so a high score there mostly shows the pipeline works, not that it generalizes.
- Do not tune the prompt on the eval notes and then present that score as generalization. Keep a version log (v1, v2, ...) with scores.
- Never commit `.env`. Check `git status` before every commit. Do not commit `mtsamples.csv` (large, public on Kaggle).
- Keep edits inside Nicole's files (`extract.py`, `extract_prompt.py`, `eval/`, scorer scripts). Avoid editing `main.py` or fixtures without coordinating.

## Run it
```
cd backend
python3 -m pip install -r requirements.txt
set -a; source .env; set +a      # loads OPENAI_API_KEY from backend/.env
python3 ../scripts/score_extraction.py
```
