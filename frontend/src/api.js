// Backend client. VITE_API_URL is the only frontend env var allowed (PRD 6.1) —
// it is a public URL, not a secret. OpenAI and FHIR never run in the browser.
const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// Guests get a per-browser sandbox via X-Session-Id (localStorage UUID;
// private-mode fallback just isolates the tab). Signed-in clinicians send a
// bearer token instead and share the unit's state — see docs/schema.md.
const SESSION_KEY = 'baton-session-id'
const TOKEN_KEY = 'baton-token'
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

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch { /* private mode — token just lives for the session */ }
}

async function req(path, { method = 'GET', body, text = false } = {}) {
  const token = getToken()
  const res = await fetch(BASE + path, {
    method,
    headers: {
      'X-Session-Id': sessionId(),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let detail = `${method} ${path} -> ${res.status}`
    try { detail = (await res.json()).detail || detail } catch { /* keep default */ }
    throw new Error(detail)
  }
  return text ? res.text() : res.json()
}

export const api = {
  // auth
  register: (email, password, name) =>
    req('/auth/register', { method: 'POST', body: { email, password, name } }),
  login: (email, password) =>
    req('/auth/login', { method: 'POST', body: { email, password } }),
  me: () => req('/auth/me'),
  logout: () => req('/auth/logout', { method: 'POST' }),
  doctors: () => req('/doctors'),
  activity: ({ patient, doctor } = {}) => {
    const q = new URLSearchParams()
    if (patient) q.set('patient', patient)
    if (doctor) q.set('doctor', doctor)
    const qs = q.toString()
    return req(`/activity${qs ? `?${qs}` : ''}`)
  },
  // panel
  listPatients: () => req('/patients'),
  // Mutations return the rebuilt patient, so callers can swap it in without a refetch.
  patchIssue: (issueId, action, value) =>
    req(`/issues/${encodeURIComponent(issueId)}`, { method: 'PATCH', body: { action, value } }),
  addNote: (pid, note) => req(`/patients/${pid}/notes`, { method: 'POST', body: note }),
  brief: () => req('/brief', { text: true }),
  health: () => req('/api/health'),
  publishBrief: () => req('/brief/publish', { method: 'POST' }),
  // Advisory AI suggestions — drafts only; the rule engine still owns issues.
  suggestClarify: (issueId) =>
    req('/suggest/clarify', { method: 'POST', body: { issue_id: issueId } }),
  suggestOwner: (issueId) =>
    req('/suggest/owner', { method: 'POST', body: { issue_id: issueId } }),
  suggestField: (issueId) =>
    req('/suggest/field', { method: 'POST', body: { issue_id: issueId } }),
  suggestHuddle: () => req('/suggest/huddle', { method: 'POST' }),
  reset: () => req('/demo/reset', { method: 'POST' }),
}
