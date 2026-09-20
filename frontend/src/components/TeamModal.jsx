import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'

// Doctor search + profile: who is on the team, which patients each has
// touched, what they did, and when. Patient names link to the patient chart.
export default function TeamModal({ patients, initial = null, onClose }) {
  const [doctors, setDoctors] = useState([])
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(initial)
  const [acts, setActs] = useState(null)
  const [actQuery, setActQuery] = useState('')
  const navigate = useNavigate()
  const ref = useRef(null)

  useEffect(() => {
    api.doctors().then(setDoctors).catch(() => setDoctors([]))
  }, [])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    ref.current?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    if (!selected) { setActs(null); return }
    setActs(null)
    setActQuery('')
    api.activity({ doctor: selected.id }).then(setActs).catch(() => setActs([]))
  }, [selected])

  const nameOf = (pid) => patients.find((p) => p.id === pid)?.name || pid
  const shown = doctors.filter((d) =>
    d.name.toLowerCase().includes(query.trim().toLowerCase()))

  const aq = actQuery.trim().toLowerCase()
  const shownActs = (acts || []).filter((a) =>
    !aq || a.text.toLowerCase().includes(aq) ||
    (a.patientId && nameOf(a.patientId).toLowerCase().includes(aq)))
  const patientCount = new Set(
    (acts || []).map((a) => a.patientId).filter(Boolean)).size

  const openPatient = (pid) => {
    onClose()
    navigate(`/patients/${pid}`)
  }

  return (
    <div
      className="ov open" role="dialog" aria-modal="true" aria-labelledby="teamt"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="modal">
        <h2 id="teamt">Team activity</h2>
        <div className="tag">Who has done what, and when.</div>
        <input
          ref={ref} className="search" value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search doctors…" aria-label="Search doctors"
        />
        <div className="chips" role="group" aria-label="Doctors">
          {shown.map((d) => (
            <button
              key={d.id}
              className={`chip${selected?.id === d.id ? ' on' : ''}`}
              onClick={() => setSelected(d)}
            >{d.name}</button>
          ))}
          {!shown.length && <span className="tag">No matching doctor.</span>}
        </div>

        {selected && (
          acts === null ? <div className="tag">Loading…</div> : (
            <>
              <div className="doc-head">
                <b>{selected.name}</b>
                <span className="tag">
                  {acts.length} action{acts.length === 1 ? '' : 's'} ·{' '}
                  {patientCount} patient{patientCount === 1 ? '' : 's'}
                </span>
              </div>
              {acts.length > 0 && (
                <input
                  className="search" value={actQuery}
                  onChange={(e) => setActQuery(e.target.value)}
                  placeholder="Filter by patient or action…"
                  aria-label="Filter this doctor's actions"
                />
              )}
              {shownActs.length ? (
                <ul className="log team-log">
                  {shownActs.map((a, k) => (
                    <li key={k}>
                      <time>{new Date(a.at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</time>
                      <span>
                        {a.text}
                        {a.patientId && (
                          <>
                            {' · '}
                            <button
                              className="who"
                              onClick={() => openPatient(a.patientId)}
                            >{nameOf(a.patientId)}</button>
                          </>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="tag">
                  {acts.length
                    ? `No actions match "${actQuery}".`
                    : `${selected.name} has no recorded actions yet.`}
                </div>
              )}
            </>
          )
        )}
        <div className="row-act">
          <button className="btn primary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}
