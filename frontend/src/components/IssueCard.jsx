import { useState } from 'react'
import { OWNERS, TYPE_LABEL, SEV_LABEL } from '../data/chart.js'
import { ago } from '../lib/rules.js'
import { SuggestBox, useSuggestion } from './Suggest.jsx'

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
  const sug = useSuggestion(actions.suggestClarify)
  const [msg, setMsg] = useState('')
  const [copied, setCopied] = useState('')

  const draft = async () => {
    await sug.run(issue.id)
    setMsg('')
    setCopied('')
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(msg || sug.data.message)
      setCopied('Copied')
    } catch {
      setCopied('')
    }
  }

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
      <div className="row-act">
        <button
          className="btn small"
          disabled={sug.loading}
          onClick={draft}
        >{sug.loading ? 'Thinking…' : 'Draft clarifying message'}</button>
        {sug.error && <span className="tag">{sug.error}</span>}
      </div>
      {sug.data?.message && (
        <SuggestBox onDismiss={sug.clear}>
          <textarea
            aria-label="Clarifying message draft"
            value={msg || sug.data.message}
            onChange={(e) => setMsg(e.target.value)}
          />
          <div className="row-act">
            <span className="tag" aria-live="polite">{copied}</span>
            <button className="btn small" onClick={copy}>Copy</button>
          </div>
        </SuggestBox>
      )}
    </>
  )
}

function HandoffBody({ issue, actions }) {
  const [value, setValue] = useState('')
  const fsug = useSuggestion(actions.suggestField)
  const osug = useSuggestion(actions.suggestOwner)

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
        {issue.fix.kind === 'field' ? (
          <button
            className="btn small"
            disabled={fsug.loading}
            onClick={() => fsug.run(issue.id)}
          >{fsug.loading ? 'Thinking…' : 'Suggest from notes'}</button>
        ) : (
          <button
            className="btn small"
            disabled={osug.loading}
            onClick={() => osug.run(issue.id)}
          >{osug.loading ? 'Thinking…' : 'Suggest owner'}</button>
        )}
      </div>
      {fsug.error && <span className="tag">{fsug.error}</span>}
      {osug.error && <span className="tag">{osug.error}</span>}
      {fsug.data && (
        <SuggestBox onDismiss={fsug.clear}>
          {fsug.data.value ? (
            <>
              <p>
                <b>{fsug.data.value}</b>
                {fsug.data.quote && <> — “{fsug.data.quote}”</>}
              </p>
              {fsug.data.source && (
                <p className="who">
                  {fsug.data.source.role}, {fsug.data.source.author},{' '}
                  {fsug.data.source.h}h ago
                </p>
              )}
              <button
                className="btn small"
                onClick={() => setValue(fsug.data.value)}
              >Use suggestion</button>
            </>
          ) : (
            <p>Nothing in the notes states this.</p>
          )}
        </SuggestBox>
      )}
      {osug.data && (
        <SuggestBox onDismiss={osug.clear}>
          {osug.data.owner ? (
            <>
              <p><b>{osug.data.owner}</b> — {osug.data.reason}</p>
              <button
                className="btn small"
                onClick={() => {
                  actions.assignPending(issue.pid, issue.fix.name, osug.data.owner)
                  osug.clear()
                }}
              >Assign {osug.data.owner}</button>
            </>
          ) : (
            <p>No clear owner from the care team.</p>
          )}
        </SuggestBox>
      )}
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
        <button
          className="btn small"
          disabled={osug.loading}
          onClick={() => osug.run(issue.id)}
        >{osug.loading ? 'Thinking…' : 'Suggest owner'}</button>
      </div>
      {osug.error && <span className="tag">{osug.error}</span>}
      {osug.data && (
        <SuggestBox onDismiss={osug.clear}>
          {osug.data.owner ? (
            <>
              <p><b>{osug.data.owner}</b> — {osug.data.reason}</p>
              <button
                className="btn small"
                onClick={() => {
                  actions.setOwner(issue.pid, issue.id, osug.data.owner, issue.title)
                  osug.clear()
                }}
              >Assign {osug.data.owner}</button>
            </>
          ) : (
            <p>No clear owner from the care team.</p>
          )}
        </SuggestBox>
      )}
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
