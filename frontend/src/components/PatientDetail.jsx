import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { DS_LABEL, FIELDS, TOPICS } from '../data/chart.js'
import { ago, handoffProgress } from '../lib/rules.js'
import IssueCard from './IssueCard.jsx'
import AddNoteForm from './AddNoteForm.jsx'

const FILTERS = [['all','All'],['conflict','Conflicts'],['handoff','Handoff gaps'],['blocker','Blockers'],['completed','Completed']]

function fmtDate(iso) {
  if (!iso) return 'Unknown date'
  // Date-only FHIR values (birthDate, onsetDate) have no timezone — parsing
  // them as UTC-midnight and rendering in local time can shift the calendar
  // day back by one for viewers west of UTC. Build the Date from local
  // y/m/d components instead so the day never moves.
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(iso)
  const d = dateOnly
    ? new Date(...iso.split('-').map((n, i) => (i === 1 ? Number(n) - 1 : Number(n))))
    : new Date(iso)
  return d.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' })
}

function InfoList({ title, items, render }) {
  if (!items.length) return null
  return (
    <>
      <div className="sec-h" style={{ marginTop: 14 }}><h3 style={{ fontSize: 15 }}>{title}</h3></div>
      <ul className="log">
        {items.map((item, k) => <li key={k}>{render(item)}</li>)}
      </ul>
    </>
  )
}

export default function PatientDetail({ patients, actions }) {
  const { patientId } = useParams()
  const [filter, setFilter] = useState('all')
  // Route component is reused across patients; reset the filter like the prototype does on select.
  useEffect(() => setFilter('all'), [patientId])
  const p = patients.find((x) => x.id === patientId)

  if (!p) {
    return (
      <main>
        <div className="empty">
          <b>Patient not found</b>
          Room {patientId} is not on 4 West. Pick a patient from the list.
        </div>
      </main>
    )
  }

  const issues = p.issues
  const st = p.dischStatus
  const hp = handoffProgress(p)
  const hotTopics = {}
  issues.forEach((i) => { if (i.type === 'conflict') hotTopics[i.topic] = true })
  const shown = filter === 'completed' ? [] : issues.filter((i) => filter === 'all' || i.type === filter)
  const notes = [...p.notes].sort((a, b) => b.seq - a.seq)
  // Ongoing/failed entries (escalated, added notes, failed FHIR writes) are
  // excluded — only genuinely resolved actions belong on a Completed tab.
  const completedLog = (p.log || []).filter((e) => e.resolved !== false)
  const counts = { all: issues.length, conflict: 0, handoff: 0, blocker: 0, completed: completedLog.length }
  issues.forEach((i) => counts[i.type]++)
  const info = p.info

  return (
    <main>
      <section className="panel pbar">
        <div className="dhead">
          <div>
            <h2>{p.name}, {p.age}</h2>
            <div className="sub">Room {p.room}. {p.dx}.</div>
            {/* PRD 12 wants every flag traceable to a chart resource, so the FHIR id
                is surfaced here. DOB and gender are deliberately NOT shown: the Synthea
                patients currently mapped to these demo ids disagree with the narrative
                age on all six (e.g. James O. reads 55 but his DOB gives 15), and showing
                a visible contradiction is worse than omitting it. Restore once the
                dataset mapping lines up. */}
            {p.fhirPatientId && (
              <div className="ident">
                <span>FHIR <b translate="no">{p.fhirPatientId}</b></span>
              </div>
            )}
            {/* Code status and allergies sit here, not in the checklist below: both are
                high-severity fields and the two a nurse needs before acting. Missing ones
                use the handoff colour, matching the amber card they also raise. */}
            <div className="vitals">
              <span className={`vital${p.handoff.codeStatus ? '' : ' warn'}`}>
                {p.handoff.codeStatus
                  ? <>Code status <b>{p.handoff.codeStatus}</b></>
                  : 'Code status missing'}
              </span>
              <span className={`vital${p.handoff.allergies ? '' : ' warn'}`}>
                {p.handoff.allergies
                  ? <>Allergies <b>{p.handoff.allergies}</b></>
                  : 'Allergies not documented'}
              </span>
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
          <h3>Patient info</h3>
          <span className="hint">From the chart, so you don't need a second system open</span>
        </div>
        {info ? (
          <>
            <div className="hgrid">
              <div className="hf ok">
                <div>
                  <div className="k">Date of birth</div>
                  <div className="v">{info.dob ? fmtDate(info.dob) : 'Unknown'}</div>
                </div>
              </div>
              <div className="hf ok">
                <div>
                  <div className="k">Sex</div>
                  <div className="v">{info.gender || 'Unknown'}</div>
                </div>
              </div>
              {info.socialHistory.map((s, k) => (
                <div className="hf ok" key={k}>
                  <div>
                    <div className="k">{s.name}</div>
                    <div className="v">{s.value || 'Recorded, no value'}</div>
                  </div>
                </div>
              ))}
            </div>
            <InfoList title="Care team" items={info.careTeam}
              render={(m) => <>{m.name}{m.role ? ` — ${m.role}` : ''}</>} />
            <InfoList title="Active problems" items={info.conditions}
              render={(c) => <>{c.name}{c.onset ? ` (since ${fmtDate(c.onset)})` : ''}</>} />
            <InfoList title="Current medications" items={info.medications}
              render={(m) => <><time>{fmtDate(m.date)}</time>{m.name}{m.dose ? ` — ${m.dose}` : ''}</>} />
            <InfoList title="Latest vitals" items={info.vitals}
              render={(v) => <><time>{fmtDate(v.date)}</time>{v.name}: {v.value || 'no value recorded'}</>} />
            <InfoList title="Latest labs" items={info.labs}
              render={(l) => <><time>{fmtDate(l.date)}</time>{l.name}: {l.value || 'no value recorded'}</>} />
            <InfoList title="Recent procedures" items={info.procedures}
              render={(p) => <><time>{fmtDate(p.date)}</time>{p.name}</>} />
            <InfoList title="Past visits" items={info.encounters}
              render={(e) => <><time>{fmtDate(e.date)}</time>{e.type || 'Encounter'}{e.reason ? ` — ${e.reason}` : ''}</>} />
          </>
        ) : (
          <div className="tag">Not available — offline/demo mode, or nothing recorded on the chart.</div>
        )}
      </section>

      <section className="panel">
        <div className="sec-h">
          <h3>{filter === 'completed' ? 'Completed' : 'What needs attention'}</h3>
          <span className="hint">
            {filter === 'completed' ? 'Resolved on this patient, most recent first' : 'Highest priority first'}
          </span>
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
        {filter === 'completed' ? (
          completedLog.length ? (
            <ul className="log">
              {completedLog.map((e, k) => (
                <li key={k}>
                  <time>{new Date(e.at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</time>
                  {e.text}
                </li>
              ))}
            </ul>
          ) : (
            <div className="empty">
              <b>Nothing completed yet</b>
              Clearing a blocker, filling a handoff field, assigning an owner, or resolving a conflict will show up here.
            </div>
          )
        ) : shown.length ? (
          shown.map((i) => (
            <IssueCard key={i.id} issue={i} actions={actions} />
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
            const v = p.handoff[f.key]
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
            const o = r.owner
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
    </main>
  )
}
