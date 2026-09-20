// Backend client. VITE_API_URL is the only frontend env var allowed (PRD 6.1) —
// it is a public URL, not a secret. OpenAI and FHIR never run in the browser.
const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function req(path, { method = 'GET', body, text = false } = {}) {
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
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
  health: () => req('/api/health'),
  publishBrief: () => req('/brief/publish', { method: 'POST' }),
  reset: () => req('/demo/reset', { method: 'POST' }),
}
