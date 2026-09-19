import { NavLink } from 'react-router-dom'
import { DS_LABEL } from '../data/chart.js'

export default function PatientList({ patients }) {
  const sorted = [...patients].sort((a, b) => b.risk - a.risk)

  return (
    <nav className="list" aria-label="Patients">
      <h2>Patients by risk</h2>
      {sorted.map((p) => {
        const st = p.dischStatus
        const c = p.issues.filter((i) => i.type === 'conflict').length
        const h = p.issues.filter((i) => i.type === 'handoff').length
        const b = p.issues.filter((i) => i.type === 'blocker').length
        return (
          <NavLink
            key={p.id}
            to={`/patients/${p.id}`}
            className={({ isActive }) => `pt${isActive ? ' sel' : ''}`}
          >
            <span className="row1">
              <span className="room">Rm {p.room}</span>
              <span className="name">{p.name}</span>
              <span className="age">{p.age}</span>
            </span>
            <span className="dx">{p.dx}</span>
            <span className="row2">
              <span className={`dch ${st}`}>Discharge in {p.dischargeInH}h: {DS_LABEL[st]}</span>
              <span className="cnts">
                <i className={`cnt ${c ? 'c' : 'z'}`} title="Conflicts">{c}</i>
                <i className={`cnt ${h ? 'h' : 'z'}`} title="Handoff gaps">{h}</i>
                <i className={`cnt ${b ? 'b' : 'z'}`} title="Blockers">{b}</i>
              </span>
            </span>
            <span className="bar">
              <span style={{ width: `${Math.min(100, Math.round((p.risk / 14) * 100))}%` }} />
            </span>
          </NavLink>
        )
      })}
    </nav>
  )
}
