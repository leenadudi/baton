import { createContext, useContext, useState } from 'react'
import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { useAuth } from './state/useAuth.js'
import { useChart } from './state/useChart.js'
import TopNav from './components/TopNav.jsx'
import SummaryTiles from './components/SummaryTiles.jsx'
import PatientList from './components/PatientList.jsx'
import PatientDetail from './components/PatientDetail.jsx'
import BriefModal from './components/BriefModal.jsx'
import LoginScreen from './components/LoginScreen.jsx'
import TeamModal from './components/TeamModal.jsx'
import { DS_LABEL } from './data/chart.js'
import { etaLabel, handoffProgress } from './lib/rules.js'

const AuthCtx = createContext(null)

const initials = (name) =>
  name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()

function StatusPill({ status }) {
  return (
    <span className="pill" title={status === 'api'
      ? 'Issues computed by the backend rule engine'
      : 'Backend unreachable — running the local demo engine'}>
      {status === 'api' ? 'Live chart' : 'Offline demo data'}
    </span>
  )
}

/* -------- dashboard: unit panel -------- */
function Dashboard({ chart, auth, onBrief, onTeam }) {
  const { patients, status, actions } = chart
  const [query, setQuery] = useState('')

  return (
    <div className="app">
      <TopNav query={query} onQuery={setQuery} status={<StatusPill status={status} />}
        onTeam={onTeam} onBrief={onBrief} auth={auth} />
      <div className="main">
        <div className="content">
          <SummaryTiles patients={patients} />
          <PatientList patients={patients} query={query} />
          <p className="foot">
            All patients, notes, and organisations in this demo are invented. Baton
            does not diagnose or recommend treatment.
            {' '}<button className="lnk" onClick={actions.reset}>Reset demo data</button>
          </p>
        </div>
      </div>
    </div>
  )
}

/* -------- patient profile -------- */
function Profile({ chart, auth, onBrief, onTeam }) {
  const { patientId } = useParams()
  const { patients, status, actions } = chart
  const p = patients.find((x) => x.id === patientId)

  return (
    <div className="app">
      <TopNav back status={<StatusPill status={status} />}
        onTeam={onTeam} onBrief={onBrief} auth={auth} />
      <div className="main">

        {p && (
          <div className="pcontext">
            <div className="who">
              <span className="ini" aria-hidden="true">{initials(p.name)}</span>
              <div>
                <div className="nm">{p.name} <span className="meta">({p.age})</span></div>
                <div className="bits">
                  <span>Room <b>{p.room}</b></span>
                  <span>{p.dx}</span>
                  {p.fhirPatientId && (
                    <span>FHIR <b className="mono" translate="no">{p.fhirPatientId}</b></span>
                  )}
                </div>
              </div>
            </div>
            <div className="grp">
              <span className={`vital${p.handoff.codeStatus ? '' : ' warn'}`}>
                {p.handoff.codeStatus ? <>Code <b>{p.handoff.codeStatus}</b></> : 'Code status missing'}
              </span>
              <span className={`vital${p.handoff.allergies ? '' : ' warn'}`}>
                {p.handoff.allergies ? <>Allergies <b>{p.handoff.allergies}</b></> : 'Allergies not documented'}
              </span>
              <span className={`dch ${p.dischStatus}`}>
                Discharge in {etaLabel(p.dischargeInH)}: {DS_LABEL[p.dischStatus]}
              </span>
              <span className="vital hp" title={`${handoffProgress(p).done} of ${handoffProgress(p).total} handoff items in place`}>
                Handoff <b>{handoffProgress(p).pct}%</b>
                <span className="track"><span style={{ width: `${handoffProgress(p).pct}%` }} /></span>
              </span>
            </div>
          </div>
        )}

        <div className="content">
          <PatientDetail patients={patients} actions={actions} />
        </div>
      </div>
    </div>
  )
}

/* Signed-in shell. Split out of App so useChart keys off the doctor: signing in
   swaps the guest sandbox for the shared unit state (see useChart). */
function Shell() {
  const auth = useContext(AuthCtx)
  const chart = useChart(auth.doctor)
  const [brief, setBrief] = useState(null)
  const [team, setTeam] = useState(false)
  const [teamDoctor, setTeamDoctor] = useState(null)

  const openBrief = () => chart.actions.getBrief().then(setBrief)
  const openTeam = () => { setTeamDoctor(null); setTeam(true) }
  const closeTeam = () => { setTeam(false); setTeamDoctor(null) }

  if (chart.status === 'loading') {
    return (
      <div className="app">
        <TopNav />
        <div className="main">
          <div className="content">
            <p className="intro" role="status" aria-live="polite">
              Loading the unit panel… <span className="tag">The API sleeps when idle, so a
              first request can take a few seconds. Demo data appears meanwhile.</span>
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <>
      <Routes>
        <Route path="/" element={<Navigate to="/patients" replace />} />
        <Route path="/patients"
          element={<Dashboard chart={chart} auth={auth} onBrief={openBrief} onTeam={openTeam} />} />
        <Route path="/patients/:patientId"
          element={<Profile chart={chart} auth={auth} onBrief={openBrief} onTeam={openTeam} />} />
        <Route path="*" element={<Navigate to="/patients" replace />} />
      </Routes>
      {brief !== null && (
        <BriefModal
          text={brief}
          onClose={() => setBrief(null)}
          canPublish={chart.status === 'api' && chart.fhirWrite}
          onPublish={chart.actions.publishBrief}
        />
      )}
      {team && (
        <TeamModal patients={chart.patients} initial={teamDoctor} onClose={closeTeam} />
      )}
    </>
  )
}

export default function App() {
  const auth = useAuth()
  const [guest, setGuest] = useState(false)

  if (auth.doctor === undefined) {
    return (
      <div className="wrap">
        <p className="intro" role="status" aria-live="polite">Loading…</p>
      </div>
    )
  }

  if (!auth.doctor && !guest) {
    return (
      <LoginScreen
        onLogin={auth.login}
        onRegister={auth.register}
        onGuest={() => setGuest(true)}
      />
    )
  }

  const ctx = {
    ...auth,
    onSignIn: () => setGuest(false),
    logout: () => { auth.logout(); setGuest(false) },
  }

  return (
    <AuthCtx.Provider value={ctx}>
      <Shell />
    </AuthCtx.Provider>
  )
}

export { AuthCtx }
