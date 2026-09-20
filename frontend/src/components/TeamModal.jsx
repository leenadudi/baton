import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

// Doctor search: who is on the team, which patients each has touched, and when.
export default function TeamModal({ patients, onClose }) {
  const [doctors, setDoctors] = useState([])
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(null)
  const [acts, setActs] = useState(null)
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
    api.activity({ doctor: selected.id }).then(setActs).catch(() => setActs([]))
  }, [selected])

  const nameOf = (pid) => patients.find((p) => p.id === pid)?.name || pid
  const shown = doctors.filter((d) =>
    d.name.toLowerCase().includes(query.trim().toLowerCase()))

  return (
    <div
      className="ov open" role="dialog" aria-modal="true" aria-labelledby="teamt"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="modal">
        <h2 id="teamt">Team activity</h2>
        <div className="tag">Who has done what on 4 West, and when.</div>
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
            acts.length ? (
              <ul className="log team-log">
                {acts.map((a, k) => (
                  <li key={k}>
                    <time>{new Date(a.at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</time>
                    <span>
                      {a.text}
                      {a.patientId && <b> · {nameOf(a.patientId)}</b>}
                    </span>
                  </li>
                ))}
              </ul>
            ) : <div className="tag">{selected.name} has no recorded actions yet.</div>
          )
        )}
        <div className="row-act">
          <button className="btn primary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}
