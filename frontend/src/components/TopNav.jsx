import { Link } from 'react-router-dom'
import Icon from './Icon.jsx'

// One bar, no sidebar: brand, optional patient search, and the actions that
// used to be split between the rail and the page header.
export default function TopNav({ query, onQuery, back, status, onTeam, onBrief, auth }) {
  return (
    <header className="topnav">
      <div className="tn-left">
        <Link className="brand-lk" to="/patients">
          <img className="mark" src="/logo.png" alt="" />
          <span>
            <span className="n">Baton</span>
            <span className="u">4 West · med-surg</span>
          </span>
        </Link>
        {back && (
          <Link className="back" to="/patients">
            <Icon name="back" /> Patients
          </Link>
        )}
      </div>

      {onQuery && (
        <div className="tn-search">
          <Icon name="search" />
          <input
            type="search" value={query} onChange={(e) => onQuery(e.target.value)}
            placeholder="Search room, name, dx" aria-label="Search patients"
            spellCheck={false} autoComplete="off"
          />
        </div>
      )}

      <div className="grp tn-right">
        {status}
        {onTeam && <button className="btn" onClick={onTeam}>Team activity</button>}
        {onBrief && <button className="btn primary" onClick={onBrief}>Shift brief</button>}
        {auth && (auth.doctor ? (
          <span className="tn-who">
            <span className="n" title="Sharing the unit view with your team">{auth.doctor.name}</span>
            <button className="btn" onClick={auth.logout}>Sign out</button>
          </span>
        ) : (
          <span className="tn-who">
            <span className="n" title="Your changes are private to this browser">Guest</span>
            <button className="btn" onClick={auth.onSignIn}>Sign in</button>
          </span>
        ))}
      </div>
    </header>
  )
}
