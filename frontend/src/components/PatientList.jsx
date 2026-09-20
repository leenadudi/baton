import { useState } from 'react'
import { Link } from 'react-router-dom'
import { DS_LABEL } from '../data/chart.js'

const TABS = [
  ['all', 'All'],
  ['risk', 'At risk'],
  ['watch', 'Watch'],
  ['ready', 'Ready'],
]
const SORTS = [
  ['risk', 'Highest risk'],
  ['discharge', 'Soonest discharge'],
  ['room', 'Room number'],
]

const initials = (name) =>
  name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()

// Table layout borrowed from the reference dashboard: aligned columns scan faster
// down a list of six than stacked cards do. Rows are links, so cmd-click and
// middle-click open a patient in a new tab.
export default function PatientList({ patients, query }) {
  const [tab, setTab] = useState('all')
  const [sort, setSort] = useState('risk')

  const q = query.trim().toLowerCase()
  const rows = patients
    .filter((p) => tab === 'all' || p.dischStatus === tab)
    .filter((p) => !q || `${p.room} ${p.name} ${p.dx}`.toLowerCase().includes(q))
    .sort((a, b) => {
      if (sort === 'discharge') return a.dischargeInH - b.dischargeInH
      if (sort === 'room') return a.room.localeCompare(b.room, undefined, { numeric: true })
      return b.risk - a.risk
    })

  const counts = { all: patients.length, risk: 0, watch: 0, ready: 0 }
  patients.forEach((p) => { counts[p.dischStatus]++ })

  return (
    <section className="tablecard">
      <div className="tc-head">
        <div>
          <h2>Patients on 4 West</h2>
          <div className="tag">Highest risk first. Open a patient to see what needs attention.</div>
        </div>
        <div className="tc-head-ctl">
          <div className="tabs" role="group" aria-label="Filter by discharge status">
            {TABS.map(([k, label]) => (
              <button key={k} className={`tab${tab === k ? ' on' : ''}`}
                aria-pressed={tab === k} onClick={() => setTab(k)}>
                {label} ({counts[k]})
              </button>
            ))}
          </div>
          <label className="sortby">
            <span>Sort by</span>
            <select value={sort} onChange={(e) => setSort(e.target.value)}>
              {SORTS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
          </label>
        </div>
      </div>

      <div className="tscroll">
        <table className="pt-table">
          <thead>
            <tr>
              <th scope="col">Room</th>
              <th scope="col">Patient</th>
              <th scope="col">Working diagnosis</th>
              <th scope="col">Discharge</th>
              <th scope="col" className="num">Conflicts</th>
              <th scope="col" className="num">Gaps</th>
              <th scope="col" className="num">Blockers</th>
              <th scope="col">Coordination risk</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const c = p.issues.filter((i) => i.type === 'conflict').length
              const h = p.issues.filter((i) => i.type === 'handoff').length
              const b = p.issues.filter((i) => i.type === 'blocker').length
              return (
                <tr key={p.id}>
                  <td><span className="rm">{p.room}</span></td>
                  <td>
                    <Link className="who" to={`/patients/${p.id}`}>
                      <span className="ini" aria-hidden="true">{initials(p.name)}</span>
                      <span>
                        <span className="nm">{p.name}</span>
                        <span className="meta"> · {p.age}</span>
                      </span>
                    </Link>
                  </td>
                  <td className="dxc">{p.dx}</td>
                  <td>
                    <span className={`dch ${p.dischStatus}`}>
                      {p.dischargeInH}h · {DS_LABEL[p.dischStatus]}
                    </span>
                  </td>
                  <td className="num"><i className={`cnt ${c ? 'c' : 'z'}`}>{c}</i></td>
                  <td className="num"><i className={`cnt ${h ? 'h' : 'z'}`}>{h}</i></td>
                  <td className="num"><i className={`cnt ${b ? 'b' : 'z'}`}>{b}</i></td>
                  <td>
                    <span className="riskbar" role="img" aria-label={`Risk score ${p.risk}`}>
                      <span style={{ width: `${Math.min(100, Math.round((p.risk / 14) * 100))}%` }} />
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {!rows.length && (
        <div className="empty" style={{ margin: 18 }}>
          <b>No patients match</b>
          {q ? `Nothing matches “${query}”.` : 'Switch tabs to see the rest of the unit.'}
        </div>
      )}
    </section>
  )
}
