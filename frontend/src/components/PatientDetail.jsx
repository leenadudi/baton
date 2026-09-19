import { useEffect, useState } from 'react'
import { useOutletContext, useParams } from 'react-router-dom'
import { DS_LABEL, FIELDS, TOPICS } from '../data/chart.js'
import { ago, allNotes, dischStatus, handoffProgress } from '../lib/rules.js'
import IssueCard from './IssueCard.jsx'
import AddNoteForm from './AddNoteForm.jsx'

const FILTERS = [['all','All'],['conflict','Conflicts'],['handoff','Handoff gaps'],['blocker','Blockers']]

export default function PatientDetail() {
  const { patientId } = useParams()
  const { rows, state, actions } = useOutletContext()
  const [filter, setFilter] = useState('all')
  // Route component is reused across patients; reset the filter like the prototype does on select.
  useEffect(() => setFilter('all'), [patientId])
  const row = rows.find((r) => r.p.id === patientId)

  if (!row) {
    return (
      <main>
        <div className="empty">
          <b>Patient not found</b>
          Room {patientId} is not on 4 West. Pick a patient from the list.
        </div>
      </main>
    )
  }

  const { p, issues } = row
  const st = dischStatus(p, issues)
  const hp = handoffProgress(p, state)
  const hotTopics = {}
  issues.forEach((i) => { if (i.type === 'conflict') hotTopics[i.topic] = true })
  const shown = issues.filter((i) => filter === 'all' || i.type === filter)
  const counts = { all: issues.length, conflict: 0, handoff: 0, blocker: 0 }
  issues.forEach((i) => counts[i.type]++)
  const notes = [...allNotes(p, state)].sort((a, b) => b.seq - a.seq)
  const log = state.log[p.id] || []

  return (
    <main>
      <section className="panel">
        <div className="dhead">
          <div>
            <h2>{p.name}, {p.age}</h2>
            <div className="sub">Room {p.room}. {p.dx}.</div>
            <div style={{ marginTop: 8 }}>
              <span className={`dch ${st}`}>Discharge in {p.dischargeInH}h: {DS_LABEL[st]}</span>
            </div>
          </div>
          <div className="meter">
            <div className="lab"><span>Handoff completeness</span><b>{hp.pct}%</b></div>
            <div className="track"><span style={{ width: `${hp.pct}%` }} /></div>
            <div className="lab" style={{ marginTop: 4 }}>
              <span>{hp.done} of {hp.total} items in place</span>
            </div>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="sec-h">
          <h3>What needs attention</h3>
          <span className="hint">Highest priority first</span>
        </div>
        <div className="chips" role="group" aria-label="Filter issues">
          {FILTERS.map(([f, label]) => (
            <button
              key={f}
              className={`chip${filter === f ? ' on' : ''}`}
              aria-pressed={filter === f}
              onClick={() => setFilter(f)}
            >{label} ({counts[f]})</button>
          ))}
        </div>
        {shown.length ? (
          shown.map((i) => (
            <IssueCard key={i.id} issue={i} owner={state.owners[i.id]} actions={actions} />
          ))
        ) : (
          <div className="empty">
            <b>{issues.length ? 'Nothing in this filter' : 'No open coordination issues'}</b>
            {issues.length
              ? 'Switch filters to see the rest.'
              : 'Instructions agree, the handoff is complete, and nothing is stuck.'}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="sec-h">
          <h3>Handoff checklist</h3>
          <span className="hint">What the next shift will be told</span>
        </div>
        <div className="hgrid">
          {FIELDS.map((f) => {
            let v = (state.filled[p.id] || {})[f.key]
            if (v === undefined) v = p.handoff[f.key]
            return (
              <div className={`hf ${v ? 'ok' : 'no'}`} key={f.key}>
                <span className="ic" aria-hidden="true">{v ? '✓' : '!'}</span>
                <div>
                  <div className="k">{f.label}</div>
                  <div className="v">{v || 'Missing'}</div>
                </div>
              </div>
            )
          })}
          {p.pending.map((r) => {
            const o = state.pendOwners[`${p.id}|${r.name}`] || r.owner
            return (
              <div className={`hf ${o ? 'ok' : 'no'}`} key={r.name}>
                <span className="ic" aria-hidden="true">{o ? '✓' : '!'}</span>
                <div>
                  <div className="k">Pending: {r.name}</div>
                  <div className="v">{o ? `Owner: ${o}` : 'No owner'}</div>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      <section className="panel">
        <div className="sec-h">
          <h3>Orders and notes</h3>
          <span className="hint">Newest first. Tags show the instruction Baton read.</span>
        </div>
        {notes.map((n) => (
          <div className="note" key={n.seq}>
            <div className="meta">
              <span className="role">{n.role}</span>
              <span>{n.author}</span>
              <span>{ago(n)}</span>
            </div>
            <div className="txt">{n.text}</div>
            <div>
              {n.tags.map((t) => (
                <span className={`tg${hotTopics[t[0]] ? ' hot' : ''}`} key={t[0]}>
                  {TOPICS[t[0]].label}: {t[1]}
                </span>
              ))}
              {n.reconcile && <span className="tg">Reconciling decision</span>}
            </div>
          </div>
        ))}
        <AddNoteForm pid={p.id} actions={actions} />
      </section>

      <section className="panel">
        <div className="sec-h"><h3>Activity</h3></div>
        {log.length ? (
          <ul className="log">
            {log.slice(0, 12).map((e, k) => (
              <li key={k}>
                <time>{new Date(e.at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</time>
                {e.text}
              </li>
            ))}
          </ul>
        ) : (
          <div className="tag">Actions taken in Baton will show up here.</div>
        )}
      </section>
    </main>
  )
}
