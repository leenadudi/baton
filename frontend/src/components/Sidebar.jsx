import { NavLink } from 'react-router-dom'
import Icon from './Icon.jsx'

// Nav items map to things Baton actually does. No placeholder destinations.
export default function Sidebar({ query, onQuery, onBrief, onReset, onTeam, auth }) {
  return (
    <aside className="side">
      <div className="side-brand">
        <img className="mark" src="/logo.png" alt="" />
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
              <button className="btn who-btn" onClick={auth.logout} title="Sign out">Sign out</button>
            </>
          ) : (
            <>
              <div className="n" title="Your changes are private to this browser">Guest sandbox</div>
              <button className="btn primary who-btn" onClick={auth.onSignIn} title="Sign in">Sign in</button>
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
