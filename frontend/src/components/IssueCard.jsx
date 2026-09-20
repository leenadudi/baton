import { useState } from 'react'
import { OWNERS, TOPICS, TYPE_LABEL, SEV_LABEL } from '../data/chart.js'
import { ago, tagOf } from '../lib/rules.js'

function OwnerSelect({ issue, actions }) {
  return (
    <select
      className={`own${issue.owner ? '' : ' un'}`}
      aria-label="Owner of this issue"
      value={issue.owner || ''}
      onChange={(e) => actions.setOwner(issue.pid, issue.id, e.target.value, issue.title)}
    >
      <option value="">Unassigned</option>
      {OWNERS.map((o) => <option key={o}>{o}</option>)}
    </select>
  )
}

function ConflictBody({ issue, actions }) {
  return (
    <>
      <p className="why">{issue.why} Pick the instruction that should stand.</p>
      <div className="opts">
        {Object.keys(issue.vals).map((v) => (
          <div className="opt" key={v}>
            <div className="oh">
              <span className="val">{v}</span>
              <button
                className="btn small"
                onClick={() => actions.adopt(issue.pid, issue.topic, v)}
              >Use this</button>
            </div>
            {issue.vals[v].map((n, k) => (
              <div key={k}>
                <div className="who"><b>{n.role}</b>, {n.author}, {ago(n)}</div>
                <blockquote>{n.text}</blockquote>
              </div>
            ))}
          </div>
        ))}
      </div>
    </>
  )
}

function HandoffBody({ issue, actions }) {
  const [value, setValue] = useState('')

  const submit = () => {
    const v = value.trim()
    if (!v) return
    if (issue.fix.kind === 'field') actions.fillField(issue.pid, issue.fix.key, v)
    else actions.assignPending(issue.pid, issue.fix.name, v)
    setValue('')
  }

  return (
    <>
      <p className="why">{issue.why}</p>
      <div className="row-act">
        {issue.fix.kind === 'field' ? (
          <input
            type="text" aria-label="Value" placeholder={issue.fix.ph}
            value={value} onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
          />
        ) : (
          <select aria-label="Result owner" value={value} onChange={(e) => setValue(e.target.value)}>
            <option value="">Choose owner</option>
            {OWNERS.concat(['Night Resident']).map((o) => <option key={o}>{o}</option>)}
          </select>
        )}
        <button className="btn small primary" onClick={submit}>
          {issue.fix.kind === 'field' ? 'Save to handoff' : 'Assign follow-up'}
        </button>
      </div>
    </>
  )
}

function BlockerBody({ issue, actions }) {
  return (
    <>
      <p className="why">{issue.sub} {issue.why}</p>
      <div className="row-act">
        <button
          className="btn small primary"
          onClick={() => actions.clearBlocker(issue.pid, issue.bid, issue.title)}
        >Mark cleared</button>
        {!issue.escalated && (
          <button
            className="btn small"
            onClick={() => actions.escalateBlocker(issue.pid, issue.bid, issue.title)}
          >Escalate</button>
        )}
      </div>
    </>
  )
}

// "Why am I seeing this?" — the rule that fired plus the evidence it ran on.
// Rendered entirely from the issue's own fields, so it works identically on
// backend issues and the offline demo engine.
function Provenance({ issue, notes }) {
  if (issue.type === 'conflict') {
    const tagged = (notes || []).filter((n) => tagOf(n, issue.topic) !== null)
    const barrier = Math.max(0, ...tagged.filter((n) => n.reconcile).map((n) => n.seq || 0))
    return (
      <>
        <p className="prov-rule">
          Rule: the newest instruction from each role disagrees on{' '}
          {TOPICS[issue.topic].label}. A reconciling note supersedes everything
          older. {tagged.length} note{tagged.length === 1 ? '' : 's'} carry this
          instruction:
        </p>
        <ul className="prov-src">
          {tagged.map((n, k) => (
            <li key={n.seq ?? k}>
              Note #{n.seq ?? '—'} · {n.role} · {n.author} — <b>{tagOf(n, issue.topic)}</b>
              {n.reconcile ? ' · reconciling' : ''}
              {!n.reconcile && (n.seq || 0) < barrier ? ' · superseded' : ''}
            </li>
          ))}
        </ul>
      </>
    )
  }
  if (issue.type === 'handoff') {
    return (
      <p className="prov-rule">
        {issue.fix?.kind === 'pending'
          ? `Rule: the pending result "${issue.fix.name}" has no owner — not on the chart, not assigned in Baton. ${issue.why}`
          : `Rule: this required handoff field is empty on the chart and nobody has filled it in Baton. ${issue.why}`}
      </p>
    )
  }
  return (
    <p className="prov-rule">
      Rule: this item is still open. {issue.sub}{' '}
      {issue.sev === 'high'
        ? 'Ranked high because it blocks a discharge due within 24h, or has waited a day or more.'
        : issue.sev === 'low'
          ? 'Ranked low because it does not block discharge and has waited under 24h.'
          : 'Ranked medium priority.'}
    </p>
  )
}

// Coordination next-step suggestion — process only, never a clinical answer.
// Server may answer with the model or the rule fallback; the card shows which.
function Suggestion({ issue, actions }) {
  const [sug, setSug] = useState(null)
  const [busy, setBusy] = useState(false)
  const load = () => {
    setBusy(true)
    Promise.resolve(actions.suggest(issue))
      .then(setSug)
      .catch(() => setSug({ text: 'Suggestion unavailable right now.', source: 'error' }))
      .finally(() => setBusy(false))
  }
  return (
    <div className="sug-wrap">
      <button className="btn small" onClick={load} disabled={busy}>
        {busy ? 'Thinking…' : 'Suggest next step'}
      </button>
      {sug && (
        <p className="sug">
          {sug.text}{' '}
          <span className="hint">
            {sug.source === 'rules' ? 'rule-based' : sug.source === 'error' ? '' : `via ${sug.source}`}
          </span>
        </p>
      )}
    </div>
  )
}

export default function IssueCard({ issue, actions, notes }) {
  return (
    <article className={`card ${issue.type}`}>
      <div className="ct">
        <span className={`badge ${issue.type}`}>{TYPE_LABEL[issue.type]}</span>
        <span className={`sev ${issue.sev}`}>{SEV_LABEL[issue.sev]}</span>
        {issue.escalated && <span className="esc">Escalated</span>}
        <OwnerSelect issue={issue} actions={actions} />
      </div>
      <h4>{issue.title}</h4>
      {issue.type === 'conflict' && <ConflictBody issue={issue} actions={actions} />}
      {issue.type === 'handoff' && <HandoffBody issue={issue} actions={actions} />}
      {issue.type === 'blocker' && <BlockerBody issue={issue} actions={actions} />}
      <Suggestion issue={issue} actions={actions} />
      <details className="prov">
        <summary>Why am I seeing this?</summary>
        <Provenance issue={issue} notes={notes} />
      </details>
    </article>
  )
}
