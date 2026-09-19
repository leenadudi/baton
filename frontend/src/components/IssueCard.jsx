import { useState } from 'react'
import { OWNERS, TYPE_LABEL, SEV_LABEL } from '../data/chart.js'
import { ago } from '../lib/rules.js'

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

export default function IssueCard({ issue, actions }) {
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
    </article>
  )
}
