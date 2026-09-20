// Detection engine ported from prototype.html (findConflicts / getIssues).
// PRD 10 names this the canonical behaviour. Once GET /patients returns `issues`,
// prefer the server engine so cards and brief cannot drift.
import { TOPICS, FIELDS, TYPE_LABEL, W } from '../data/chart.js'

// Hours read fine up to a day; past that "44h" makes you do arithmetic to see
// it is not today. Switch to days + hours at the 24h boundary.
export function etaLabel(h) {
  if (h < 24) return `${h}h`
  const d = Math.floor(h / 24)
  const rem = h % 24
  return rem ? `${d}d ${rem}h` : `${d}d`
}

export function allNotes(p, state) {
  return p.notes.concat(state.added[p.id] || [])
}

export function tagOf(n, topic) {
  const t = n.tags.find((x) => x[0] === topic)
  return t ? t[1] : null
}

// Deterministic coordination suggestion for offline/mock mode — mirrors the
// fallback branch of backend/app/suggest.py. Process steps only, never a
// clinical answer, and never a winner when instructions conflict.
export function suggestFor(issue) {
  let text
  if (issue.type === 'conflict') {
    const roles = [...new Set(
      Object.values(issue.vals || {}).flat().map((n) => n.role).filter(Boolean),
    )].sort()
    text = `Have the attending reconcile this one — ask ${roles.join(' and ') || 'each team'} ` +
      'to confirm which instruction was last carried out before anyone follows ' +
      'either. Baton flags conflicts; it does not pick the winner.'
  } else if (issue.type === 'handoff') {
    text = issue.fix?.kind === 'pending'
      ? 'Assign a named owner for this pending result before shift change — ' +
        'unowned follow-ups are the ones that come back abnormal and go unseen.'
      : 'Fill this field before the next shift takes over — it is required ' +
        'for a complete handoff.'
  } else {
    text = issue.escalated
      ? 'Escalation is logged — confirm the charge nurse or bed coordinator ' +
        'has seen it, and note the expected resolution time in the handoff.'
      : 'Assign an owner and confirm with whoever it is waiting on; if it has ' +
        'not moved by the next check-in, escalate to the charge nurse.'
  }
  return { text, source: 'rules' }
}

export function ago(n) {
  if (n.at) {
    const m = Math.round((Date.now() - n.at) / 60000)
    return m < 1 ? 'just now' : m < 60 ? `${m}m ago` : `${Math.round(m / 60)}h ago`
  }
  return `${n.h}h ago`
}

export function findConflicts(p, state) {
  const notes = allNotes(p, state)
  const out = []
  Object.keys(TOPICS).forEach((topic) => {
    const tn = notes.filter((n) => tagOf(n, topic) !== null)
    if (!tn.length) return
    // Adopting a value writes a reconciling note; older instructions stop counting.
    let barrier = 0
    tn.forEach((n) => { if (n.reconcile && n.seq > barrier) barrier = n.seq })
    const latest = {}
    tn.filter((n) => n.seq >= barrier).forEach((n) => {
      if (!latest[n.role] || n.seq > latest[n.role].seq) latest[n.role] = n
    })
    const vals = {}
    Object.keys(latest).forEach((r) => {
      const n = latest[r]
      const v = tagOf(n, topic)
      ;(vals[v] = vals[v] || []).push(n)
    })
    if (Object.keys(vals).length > 1) out.push({ topic, vals })
  })
  return out
}

export function getIssues(p, state) {
  const issues = []

  findConflicts(p, state).forEach((c) => {
    const T = TOPICS[c.topic]
    const vs = Object.keys(c.vals)
    const sub = []
    vs.forEach((v) => c.vals[v].forEach((n) => sub.push(`${n.role}: ${v}`)))
    issues.push({
      id: `${p.id}:conflict:${c.topic}`, pid: p.id, type: 'conflict', sev: T.sev,
      title: `${T.label}: ${vs.length} different instructions are active`,
      sub: sub.join('; '),
      why: 'Both cannot be followed. Until someone picks one, whoever reads the chart next may follow either.',
      topic: c.topic, vals: c.vals,
    })
  })

  FIELDS.forEach((f) => {
    let v = (state.filled[p.id] || {})[f.key]
    if (v === undefined) v = p.handoff[f.key]
    if (!v) {
      issues.push({
        id: `${p.id}:handoff:${f.key}`, pid: p.id, type: 'handoff', sev: f.sev,
        title: `${f.label} is missing from the handoff`,
        sub: f.why, why: f.why, fix: { kind: 'field', key: f.key, ph: f.ph },
      })
    }
  })

  p.pending.forEach((r) => {
    const o = state.pendOwners[`${p.id}|${r.name}`] || r.owner
    if (!o) {
      issues.push({
        id: `${p.id}:handoff:pend:${r.name}`, pid: p.id, type: 'handoff', sev: 'med',
        title: `Pending result has no owner: ${r.name}`,
        sub: 'Result pending, nobody assigned to follow it up',
        why: 'If nobody owns a pending result, it can come back abnormal and go unseen after the patient leaves.',
        fix: { kind: 'pending', name: r.name },
      })
    }
  })

  p.blockers.forEach((b) => {
    if ((state.cleared[p.id] || {})[b.id]) return
    let sev = 'med'
    if (b.blocks && (p.dischargeInH <= 24 || b.ageH >= 24)) sev = 'high'
    else if (!b.blocks && b.ageH < 24) sev = 'low'
    issues.push({
      id: `${p.id}:blocker:${b.id}`, pid: p.id, type: 'blocker', sev,
      title: b.label,
      sub: `Waiting on ${b.waitingOn} for ${b.ageH}h. Discharge target in ${etaLabel(p.dischargeInH)}.`,
      why: b.cat + (b.blocks ? ' item that blocks discharge.' : ' item.'),
      bid: b.id, escalated: !!state.escalated[`${p.id}|${b.id}`],
    })
  })

  issues.sort((a, b) => W[b.sev] - W[a.sev])
  return issues
}

export function riskOf(issues) {
  return issues.reduce((a, i) => a + W[i.sev], 0)
}

export function dischStatus(p, issues) {
  if (issues.some((i) => i.sev === 'high')) return 'risk'
  return issues.length ? 'watch' : 'ready'
}

// Takes an already-overlaid patient, so it works the same on API and mock data.
export function handoffProgress(p) {
  const total = FIELDS.length + p.pending.length
  let done = 0
  FIELDS.forEach((f) => { if (p.handoff[f.key]) done++ })
  p.pending.forEach((r) => { if (r.owner) done++ })
  return { done, total, pct: Math.round((done / total) * 100) }
}

// Unit-wide brief. PRD 8.1 pins GET /brief to this shape: severity, then soonest
// discharge, cap 14 with a remainder line. Never written back to the chart.
export function briefText(patients, state) {
  const all = []
  patients.forEach((p) => getIssues(p, state).forEach((i) => all.push({ p, i })))
  all.sort((a, b) => W[b.i.sev] - W[a.i.sev] || a.p.dischargeInH - b.p.dischargeInH)
  const un = all.filter((x) => !state.owners[x.i.id]).length
  const L = [
    'SHIFT HANDOFF BRIEF (synthetic data)',
    `${all.length} open coordination issues, ${un} with no owner.`,
    '',
  ]
  if (!all.length) L.push('Nothing open. Instructions agree, handoffs are complete, no blockers.')
  all.slice(0, 14).forEach((x, k) => {
    L.push(`${k + 1}. [${x.i.sev.toUpperCase()}] Rm ${x.p.room} ${x.p.name}: ${TYPE_LABEL[x.i.type]}. ${x.i.title}.`)
    L.push(`   ${x.i.sub}`)
    L.push(`   Owner: ${state.owners[x.i.id] || 'UNASSIGNED'}; discharge target in ${etaLabel(x.p.dischargeInH)}.`)
    L.push('')
  })
  if (all.length > 14) L.push(`+ ${all.length - 14} lower-priority items in Baton.`)
  return L.join('\n')
}
