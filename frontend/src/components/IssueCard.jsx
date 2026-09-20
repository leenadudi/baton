import { useState } from 'react'
import { OWNERS, TYPE_LABEL, SEV_LABEL } from '../data/chart.js'
import { ago } from '../lib/rules.js'
import { SuggestBox, SuggestButton, useSuggestion } from './Suggest.jsx'

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

function OwnerSuggestion({ sug, onAssign }) {
  if (!sug.data) return null
  return (
    <SuggestBox onDismiss={sug.clear}>
      {sug.data.owner ? (
        <div className="srow">
          <p><b>{sug.data.owner}</b> <span className="muted">— {sug.data.reason}</span></p>
          <button className="btn small primary" onClick={() => { onAssign(sug.data.owner); sug.clear() }}>
            Assign {sug.data.owner}
          </button>
        </div>
      ) : (
        <p className="muted">No clear owner on the care team.</p>
      )}
    </SuggestBox>
  )
}

function ConflictBody({ issue, actions }) {
  return (
    <>
      <p className="why">{issue.why} Pick the instruction that should stand — Baton never picks for you.</p>
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
                <div className="who"><b>{n.role}</b> · {n.author} · {ago(n)}</div>
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
  const fsug = useSuggestion(actions.suggestField)
  const osug = useSuggestion(actions.suggestOwner)
  const isField = issue.fix.kind === 'field'

  const submit = () => {
    const v = value.trim()
    if (!v) return
    if (isField) actions.fillField(issue.pid, issue.fix.key, v)
    else actions.assignPending(issue.pid, issue.fix.name, v)
    setValue('')
  }

  return (
    <>
      <p className="why">{issue.why}</p>
      <div className="row-act">
        {isField ? (
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
          {isField ? 'Save to handoff' : 'Assign follow-up'}
        </button>
        {isField ? (
          <SuggestButton loading={fsug.loading} onClick={() => fsug.run(issue.id)}>Find it in the notes</SuggestButton>
        ) : (
          <SuggestButton loading={osug.loading} onClick={() => osug.run(issue.id)}>Suggest an owner</SuggestButton>
        )}
      </div>
      {fsug.error && <span className="tag">{fsug.error}</span>}
      {osug.error && <span className="tag">{osug.error}</span>}
      {fsug.data && (
        <SuggestBox onDismiss={fsug.clear} label="Found in the notes">
          {fsug.data.value ? (
            <div className="srow">
              <div>
                <p><b>{fsug.data.value}</b></p>
                {fsug.data.quote && <blockquote>“{fsug.data.quote}”</blockquote>}
                {fsug.data.source && (
                  <p className="who">
                    {fsug.data.source.role} · {fsug.data.source.author} · {fsug.data.source.h}h ago
                  </p>
                )}
              </div>
              <button className="btn small primary" onClick={() => { setValue(fsug.data.value); fsug.clear() }}>
                Use this value
              </button>
            </div>
          ) : (
            <p className="muted">Nothing in the notes states this — it needs a human.</p>
          )}
        </SuggestBox>
      )}
      <OwnerSuggestion sug={osug} onAssign={(o) => actions.assignPending(issue.pid, issue.fix.name, o)} />
    </>
  )
}

function BlockerBody({ issue, actions }) {
  const osug = useSuggestion(actions.suggestOwner)
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
        {!issue.owner && (
          <SuggestButton loading={osug.loading} onClick={() => osug.run(issue.id)}>Suggest an owner</SuggestButton>
        )}
      </div>
      {osug.error && <span className="tag">{osug.error}</span>}
      <OwnerSuggestion sug={osug} onAssign={(o) => actions.setOwner(issue.pid, issue.id, o, issue.title)} />
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
