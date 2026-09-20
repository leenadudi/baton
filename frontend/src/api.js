// Backend client. VITE_API_URL is the only frontend env var allowed (PRD 6.1) —
// it is a public URL, not a secret. OpenAI and FHIR never run in the browser.
const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// Demo state is per-session on the server: each browser gets its own sandbox so
// one judge's clicks never change another judge's panel. The id lives in
// localStorage; private-mode fallback just isolates the tab.
const SESSION_KEY = 'baton-session-id'
let _sid = null
function sessionId() {
  if (_sid) return _sid
  try {
    _sid = localStorage.getItem(SESSION_KEY)
    if (!_sid) {
      _sid = crypto.randomUUID()
      localStorage.setItem(SESSION_KEY, _sid)
    }
  } catch {
    _sid = `tab-${Math.random().toString(36).slice(2)}`
  }
  return _sid
}

async function req(path, { method = 'GET', body, text = false } = {}) {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      'X-Session-Id': sessionId(),
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status}`)
  return text ? res.text() : res.json()
}

export const api = {
  listPatients: () => req('/patients'),
  // Mutations return the rebuilt patient, so callers can swap it in without a refetch.
  patchIssue: (issueId, action, value) =>
    req(`/issues/${encodeURIComponent(issueId)}`, { method: 'PATCH', body: { action, value } }),
  addNote: (pid, note) => req(`/patients/${pid}/notes`, { method: 'POST', body: note }),
  brief: () => req('/brief', { text: true }),
  reset: () => req('/demo/reset', { method: 'POST' }),
}
