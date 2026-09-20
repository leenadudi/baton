import { NavLink } from 'react-router-dom'
import Icon from './Icon.jsx'

// Nav items map to things Baton actually does. No placeholder destinations.
export default function Sidebar({ query, onQuery, onBrief, onReset, onTeam, auth }) {
  return (
    <aside className="side">
      <div className="side-brand">
        <svg className="mark" viewBox="0 0 44 44" aria-hidden="true">
          <rect width="44" height="44" rx="11" fill="var(--nav-ink)" />
          <circle cx="12" cy="22" r="5" fill="var(--nav)" />
          <rect x="17" y="19.5" width="12" height="5" rx="2.5" fill="var(--nav)" />
          <circle cx="32" cy="22" r="5" fill="none" stroke="var(--nav)" strokeWidth="2.5" strokeDasharray="3.2 2.6" />
        </svg>
        <div>
          <div className="n">Baton</div>
          <div className="u">4 West · med-surg</div>
        </div>
      </div>

      {onQuery && (
        <div className="side-search">
          <Icon name="search" />
          <input
            type="search" value={query} onChange={(e) => onQuery(e.target.value)}
            placeholder="Search room, name, dx" aria-label="Search patients"
            spellCheck={false} autoComplete="off"
          />
        </div>
      )}

      <div className="side-lbl">Unit</div>
      <NavLink to="/patients" end className={({ isActive }) => `nav-i${isActive ? ' on' : ''}`}>
        <Icon name="grid" /><span>Unit panel</span>
      </NavLink>

      <div className="side-lbl">Handoff</div>
      <button className="nav-i" onClick={onBrief}>
        <Icon name="brief" /><span>Shift brief</span>
      </button>
      <button className="nav-i" onClick={onReset}>
        <Icon name="reset" /><span>Reset demo</span>
      </button>
      {onTeam && (
        <button className="nav-i" onClick={onTeam}>
          <Icon name="grid" /><span>Team activity</span>
        </button>
      )}

      {auth && (
        <div className="side-who">
          {auth.doctor ? (
            <>
              <div className="n" title="Sharing the unit view with your team">{auth.doctor.name}</div>
              <button className="lnk" onClick={auth.logout}>Sign out</button>
            </>
          ) : (
            <>
              <div className="n" title="Your changes are private to this browser">Guest sandbox</div>
              <button className="lnk" onClick={auth.onSignIn}>Sign in</button>
            </>
          )}
        </div>
      )}

      <div className="side-foot">
        Synthetic data, no PHI. Baton is a coordination aid and does not replace
        clinical judgment.
      </div>
    </aside>
  )
}
