// Demo-local state (prototype.html 351-359). Not the chart — Baton never writes back.
// PRD 8.1: backend demo mutations may be in-memory only, so this stays useful.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { TOPICS, FIELDS } from '../data/chart.js'

const KEY = 'baton-demo-v1'

export function freshState() {
  return { added:{}, filled:{}, cleared:{}, escalated:{}, pendOwners:{}, owners:{}, log:{}, nextSeq:1000 }
}

function load() {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return { ...freshState(), ...JSON.parse(raw) }
  } catch { /* private mode / quota — fall through to a fresh demo */ }
  return freshState()
}

export function useDemoState() {
  const [state, setState] = useState(load)

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(state)) } catch { /* ignore */ }
  }, [state])

  const logged = useCallback((s, pid, text) => ({
    ...s,
    log: { ...s.log, [pid]: [{ at: Date.now(), text }, ...(s.log[pid] || [])] },
  }), [])

  const appendNote = useCallback((s, pid, note) => ({
    ...s,
    nextSeq: s.nextSeq + 1,
    added: { ...s.added, [pid]: [...(s.added[pid] || []), { ...note, seq: s.nextSeq, at: Date.now() }] },
  }), [])

  const actions = useMemo(() => ({
    adopt: (pid, topic, value) => setState((s) => {
      const T = TOPICS[topic]
      const next = appendNote(s, pid, {
        role: 'Attending decision', author: 'Reconciled in Baton',
        text: `Reconciled ${T.label}: proceed with ${value}. Earlier conflicting instructions are superseded.`,
        tags: [[topic, value]], reconcile: true,
      })
      return logged(next, pid, `Reconciled ${T.label} to ${value}`)
    }),

    fillField: (pid, key, value) => setState((s) => {
      const next = { ...s, filled: { ...s.filled, [pid]: { ...(s.filled[pid] || {}), [key]: value } } }
      const f = FIELDS.find((x) => x.key === key)
      return logged(next, pid, `Added ${f.label} to handoff`)
    }),

    assignPending: (pid, name, owner) => setState((s) => {
      const next = { ...s, pendOwners: { ...s.pendOwners, [`${pid}|${name}`]: owner } }
      return logged(next, pid, `Assigned ${name} follow-up to ${owner}`)
    }),

    clearBlocker: (pid, bid, label) => setState((s) => {
      const next = { ...s, cleared: { ...s.cleared, [pid]: { ...(s.cleared[pid] || {}), [bid]: true } } }
      return logged(next, pid, `Cleared blocker: ${label}`)
    }),

    escalateBlocker: (pid, bid, label) => setState((s) => {
      const next = { ...s, escalated: { ...s.escalated, [`${pid}|${bid}`]: true } }
      return logged(next, pid, `Escalated blocker: ${label}`)
    }),

    addNote: (pid, { role, topic, value, text }) => setState((s) => {
      const body = text || `${TOPICS[topic].label}: ${value}.`
      const next = appendNote(s, pid, {
        role, author: `${role} (you)`, text: body, tags: topic ? [[topic, value]] : [],
      })
      const suffix = topic ? ` (${TOPICS[topic].label}: ${value})` : ''
      return logged(next, pid, `Added ${role} note${suffix}`)
    }),

    setOwner: (pid, issueId, owner, issueTitle) => setState((s) => {
      const owners = { ...s.owners }
      if (owner) owners[issueId] = owner
      else delete owners[issueId]
      const next = { ...s, owners }
      return owner ? logged(next, pid, `Assigned "${issueTitle}" to ${owner}`) : next
    }),

    reset: () => setState(freshState()),
  }), [appendNote, logged])

  return [state, actions]
}
