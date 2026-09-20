// Single source of patients for the UI.
//
// Prefers the backend: PRD 10 says once GET /patients returns `issues`, the server
// is the one engine so cards and brief cannot drift. Falls back to the local mock
// engine when the API is unreachable — PRD 6.1 warns Render Free sleeps after idle,
// and a cold backend must not mean a blank demo in front of judges.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { FIELDS, PATIENTS } from '../data/chart.js'
import { allNotes, briefText, dischStatus, getIssues, riskOf } from '../lib/rules.js'
import { useDemoState } from './useDemoState.js'

const COLD_START_MS = 6000

// Reshape a mock patient + demo state into exactly what GET /patients returns.
function normalize(p, s) {
  const issues = getIssues(p, s).map((i) => ({ ...i, owner: s.owners[i.id] || null }))
  return {
    ...p,
    handoff: Object.fromEntries(FIELDS.map((f) => {
      const v = (s.filled[p.id] || {})[f.key]
      return [f.key, v === undefined ? p.handoff[f.key] : v]
    })),
    pending: p.pending.map((r) => ({ ...r, owner: s.pendOwners[`${p.id}|${r.name}`] || r.owner })),
    notes: allNotes(p, s),
    issues,
    log: s.log[p.id] || [],
    risk: riskOf(issues),
    dischStatus: dischStatus(p, issues),
  }
}

export function useChart(doctor) {
  const [mockState, mockActions] = useDemoState()
  const [served, setServed] = useState(null)
  const [status, setStatus] = useState('loading') // loading | api | mock
  const [fhirWrite, setFhirWrite] = useState(false)

  // Refetch when auth changes: signing in switches from the guest sandbox to
  // the shared unit state on the server.
  useEffect(() => {
    let live = true
    // Render Free cold-starts take up to a minute and fetch has no default
    // deadline, so without this the panel sits on "Loading…" indefinitely.
    // Show the local engine meanwhile; the .then below upgrades to live data
    // whenever the backend does wake up.
    const coldStart = setTimeout(
      () => { if (live) setStatus((cur) => (cur === 'loading' ? 'mock' : cur)) },
      COLD_START_MS,
    )
    api.listPatients()
      .then((ps) => { if (live) { setServed(ps); setStatus('api') } })
      .catch(() => { if (live) setStatus('mock') })
      .finally(() => clearTimeout(coldStart))
    api.health().then((h) => { if (live) setFhirWrite(!!h?.panel?.fhir_write) }).catch(() => {})
    return () => { live = false; clearTimeout(coldStart) }
  }, [doctor])

  // Signed-in clinicians share the unit — poll so a teammate's actions show up.
  useEffect(() => {
    if (status !== 'api' || !doctor) return undefined
    const t = setInterval(() => {
      api.listPatients().then(setServed).catch(() => {})
    }, 8000)
    return () => clearInterval(t)
  }, [status, doctor])

  const patients = useMemo(
    () => (status === 'api' && served ? served : PATIENTS.map((p) => normalize(p, mockState))),
    [status, served, mockState],
  )

  // Mutations return the rebuilt patient; swap it in rather than refetching the panel.
  const swap = useCallback((updated) => {
    setServed((cur) => (cur || []).map((p) => (p.id === updated.id ? updated : p)))
  }, [])

  const onApi = status === 'api'

  const actions = useMemo(() => ({
    setOwner: (pid, issueId, owner, title) => onApi
      ? api.patchIssue(issueId, 'owner', owner || null).then(swap)
      : mockActions.setOwner(pid, issueId, owner, title),

    fillField: (pid, key, value) => onApi
      ? api.patchIssue(`${pid}:handoff:${key}`, 'fill', value).then(swap)
      : mockActions.fillField(pid, key, value),

    assignPending: (pid, name, owner) => onApi
      ? api.patchIssue(`${pid}:handoff:pend:${name}`, 'pendingOwner', owner).then(swap)
      : mockActions.assignPending(pid, name, owner),

    clearBlocker: (pid, bid, label) => onApi
      ? api.patchIssue(`${pid}:blocker:${bid}`, 'clear').then(swap)
      : mockActions.clearBlocker(pid, bid, label),

    escalateBlocker: (pid, bid, label) => onApi
      ? api.patchIssue(`${pid}:blocker:${bid}`, 'escalate').then(swap)
      : mockActions.escalateBlocker(pid, bid, label),

    adopt: (pid, topic, value) => onApi
      ? api.patchIssue(`${pid}:conflict:${topic}`, 'adopt', value).then(swap)
      : mockActions.adopt(pid, topic, value),

    addNote: (pid, note) => onApi
      ? api.addNote(pid, note).then(swap)
      : mockActions.addNote(pid, note),

    reset: () => onApi
      ? api.reset().then(api.listPatients).then(setServed)
      : mockActions.reset(),

    // Server owns the brief when available, so it cannot drift from the cards.
    getBrief: () => onApi ? api.brief() : Promise.resolve(briefText(PATIENTS, mockState)),

    publishBrief: () => api.publishBrief(),

    // Advisory suggestions exist only against the live backend.
    suggestClarify: (issueId) => onApi ? api.suggestClarify(issueId)
      : Promise.reject(new Error('AI suggestions need the live backend')),
    suggestOwner: (issueId) => onApi ? api.suggestOwner(issueId)
      : Promise.reject(new Error('AI suggestions need the live backend')),
    suggestField: (issueId) => onApi ? api.suggestField(issueId)
      : Promise.reject(new Error('AI suggestions need the live backend')),
    suggestHuddle: () => onApi ? api.suggestHuddle()
      : Promise.reject(new Error('AI suggestions need the live backend')),
  }), [onApi, swap, mockActions, mockState])

  return { patients, status, actions, fhirWrite }
}
