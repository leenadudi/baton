import { useState } from 'react'
import { Link, Navigate, Route, Routes, useParams } from 'react-router-dom'
import { useChart } from './state/useChart.js'
import Sidebar from './components/Sidebar.jsx'
import Icon from './components/Icon.jsx'
import SummaryTiles from './components/SummaryTiles.jsx'
import PatientList from './components/PatientList.jsx'
import PatientDetail from './components/PatientDetail.jsx'
import BriefModal from './components/BriefModal.jsx'
import { DS_LABEL } from './data/chart.js'

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
function Dashboard({ chart, onBrief }) {
  const { patients, status, actions } = chart
  const [query, setQuery] = useState('')

  return (
    <div className="app">
      <Sidebar query={query} onQuery={setQuery} onBrief={onBrief} onReset={actions.reset} />
      <div className="main">
        <header className="topbar">
          <div>
            <h1>Unit panel</h1>
            <div className="sub">
              Every open coordination issue on 4 West — conflicting instructions,
              incomplete handoffs, and administrative work that has stopped moving.
            </div>
          </div>
          <div className="grp">
            <StatusPill status={status} />
            <button className="btn primary" onClick={onBrief}>Shift brief</button>
          </div>
        </header>

        <div className="content">
          <SummaryTiles patients={patients} />
          <PatientList patients={patients} query={query} />
          <p className="foot">
            All patients, notes, and organisations in this demo are invented. Baton
            does not diagnose or recommend treatment.
          </p>
        </div>
      </div>
    </div>
  )
}

/* -------- patient profile -------- */
function Profile({ chart, onBrief }) {
  const { patientId } = useParams()
  const { patients, status, actions } = chart
  const p = patients.find((x) => x.id === patientId)

  return (
    <div className="app iconrail">
      <Sidebar onBrief={onBrief} onReset={actions.reset} />
      <div className="main">
        <header className="topbar">
          <Link className="back" to="/patients">
            <Icon name="back" /> Patients
          </Link>
          <div className="grp">
            <StatusPill status={status} />
            <button className="btn primary" onClick={onBrief}>Shift brief</button>
          </div>
        </header>

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
              <span className={`dch ${p.dischStatus}`}>
                Discharge in {p.dischargeInH}h: {DS_LABEL[p.dischStatus]}
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

export default function App() {
  const chart = useChart()
  const [brief, setBrief] = useState(null)
  const openBrief = () => chart.actions.getBrief().then(setBrief)

  if (chart.status === 'loading') {
    return (
      <div className="app">
        <Sidebar onBrief={() => {}} onReset={() => {}} />
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
        <Route path="/patients" element={<Dashboard chart={chart} onBrief={openBrief} />} />
        <Route path="/patients/:patientId" element={<Profile chart={chart} onBrief={openBrief} />} />
        <Route path="*" element={<Navigate to="/patients" replace />} />
      </Routes>
      {brief !== null && <BriefModal text={brief} onClose={() => setBrief(null)} />}
    </>
  )
}
