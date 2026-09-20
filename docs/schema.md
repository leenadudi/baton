# Baton data model — auth, shared unit state, and the audit trail

Persistence layer: `backend/app/store.py`. Two backends behind one interface:

- **`MongoStore`** — used when `MONGODB_URI` is set (MongoDB Atlas `baton`
  database). State and history survive restarts.
- **`MemoryStore`** — used when it is not. Same behavior, nothing persisted;
  local dev, tests, and a cold Render boot all still work.

All chart data remains read-only FHIR. Nothing below is clinical data — it is
demo coordination state, and only for synthetic patients.

## Scopes

Every demo state and every action belongs to a **scope**:

| Scope key | Who shares it |
|---|---|
| `unit` | All signed-in clinicians — one shared view, like a real unit |
| `session:<id>` | One guest browser (`X-Session-Id` header, capped at 128 chars). Sandboxed so an anonymous visitor cannot touch the team demo |

The frontend sends `Authorization: Bearer <token>` when signed in (scope =
`unit`), otherwise `X-Session-Id` (scope = `session:<id>`).

## Collections (Mongo) / maps (memory)

### `users`

| Field | Type | Notes |
|---|---|---|
| `_id` / `id` | string | 16-hex random id |
| `email` | string | lowercased; unique index (Mongo) |
| `name` | string | display name shown on actions, e.g. "Dr. Rivera" |
| `salt` | string | per-user, hex |
| `pwHash` | string | PBKDF2-HMAC-SHA256, 60k iterations. Never returned by the API |
| `createdAt` | int (epoch ms) | |

### `tokens`

| Field | Type | Notes |
|---|---|---|
| `_id` | string | the bearer token itself (`token_urlsafe(32)`) |
| `userId` | string | → `users._id` |
| `createdAt` | datetime | TTL index: expires 7 days |

### `states`

| Field | Type | Notes |
|---|---|---|
| `_id` | string | the scope (`unit` or `session:<id>`) |
| `data` | object | the demo state dict: `added`, `filled`, `cleared`, `escalated`, `pendOwners`, `owners`, `log`, `nextSeq` — the in-memory shape the rule engine already consumes |
| `updatedAt` | int (epoch ms) | session scopes idle > 6 h are pruned |

### `actions` — the audit trail

One record per mutation; backs both search directions.

| Field | Type | Notes |
|---|---|---|
| `scope` | string | which unit/session this happened in |
| `at` | int (epoch ms) | timestamp → the timeline |
| `doctorId` | string \| null | → `users._id`; null for guests |
| `doctorName` | string | denormalized for display ("Guest" when signed out) |
| `patientId` | string \| null | e.g. `p1`; null for unit-wide actions (`reset`) |
| `action` | string | `addNote`, `owner`, `fill`, `pendingOwner`, `clear`, `escalate`, `adopt`, `reset` |
| `target` | string \| null | the issue id acted on, e.g. `p1:blocker:b1` |
| `text` | string | human summary, e.g. "Cleared blocker: PT/INR result" |

Indexes: `(scope, patientId)`, `(scope, doctorId)`, `(scope, at desc)`.

## API surface

| Route | Auth | Purpose |
|---|---|---|
| `POST /auth/register` | — | `{email, password, name}` → `{token, doctor}`; 409 on duplicate email |
| `POST /auth/login` | — | `{email, password}` → `{token, doctor}`; 401 on bad credentials |
| `GET /auth/me` | Bearer | current doctor; 401 if not signed in |
| `POST /auth/logout` | Bearer | revoke token |
| `GET /doctors` | — | registered clinicians `{id, name}` (doctor search) |
| `GET /activity?patient=&doctor=` | Bearer or session | scope-filtered action records, newest first, cap 200 |
| `GET /patients`, `PATCH /issues/:id`, `POST /patients/:id/notes`, `GET /brief`, `POST /demo/reset` | Bearer or session | same routes as before, resolved against the caller's scope; every mutation writes an `actions` record |

`POST /demo/reset` clears the caller's whole scope (state + audit trail) and
then records who reset it, so the trail always shows the reset itself.

## What is deliberately absent

- No roles/permissions — every signed-in clinician can do everything (demo).
- No email verification, password reset, or rate limiting — hackathon scope.
- Session ids and bearer tokens are isolation/identity for a demo, not
  hardened auth. Nothing in the store is PHI or a real credential.
