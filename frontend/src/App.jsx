import { useMemo, useState } from 'react'
import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { PATIENTS } from './data/chart.js'
import { briefText, getIssues } from './lib/rules.js'
import { useDemoState } from './state/useDemoState.js'
import SummaryTiles from './components/SummaryTiles.jsx'
import PatientList from './components/PatientList.jsx'
import PatientDetail from './components/PatientDetail.jsx'
import BriefModal from './components/BriefModal.jsx'

function Panel() {
  const [state, actions] = useDemoState()
  const [briefOpen, setBriefOpen] = useState(false)
  const rows = useMemo(
    () => PATIENTS.map((p) => ({ p, issues: getIssues(p, state) })),
    [state],
  )

  return (
    <div className="wrap">
      <header className="top">
        <div className="brand">
          <svg className="mark" viewBox="0 0 44 44" aria-hidden="true">
            <rect width="44" height="44" rx="11" fill="var(--ink)" />
            <circle cx="12" cy="22" r="5" fill="var(--bg)" />
            <rect x="17" y="19.5" width="12" height="5" rx="2.5" fill="var(--bg)" />
            <circle cx="32" cy="22" r="5" fill="none" stroke="var(--bg)" strokeWidth="2.5" strokeDasharray="3.2 2.6" />
          </svg>
          <div>
            <h1>Baton</h1>
            <div className="tag">Find what falls between care team members before the patient does</div>
          </div>
        </div>
        <div className="actions">
          <span className="pill"><b>4 West</b> medical-surgical unit</span>
          <span className="pill">Synthetic data, no PHI</span>
          <button className="btn primary" onClick={() => setBriefOpen(true)}>Shift brief</button>
          <button className="btn ghost" onClick={actions.reset}>Reset demo</button>
        </div>
      </header>

      <p className="intro">
        Baton reads the trail of orders, notes, and tasks around each patient and flags three kinds
        of coordination failure: teams giving conflicting instructions, handoffs with missing pieces,
        and administrative tasks stuck with nobody moving them. It does not diagnose or recommend treatment.
      </p>

      <details className="how">
        <summary>How Baton decides what to flag</summary>
        <ul>
          <li><b>Conflicting instructions:</b> each note can carry a structured instruction (for example, Diet: NPO). If the latest instruction from two or more roles on the same topic disagree, Baton flags it. Choosing a source of truth records a reconciling decision, and older instructions stop counting.</li>
          <li><b>Incomplete handoffs:</b> required handoff fields (code status, allergies, family contact, follow-up owner, medication reconciliation) that are empty, and pending results that nobody owns.</li>
          <li><b>Administrative blockers:</b> authorizations, referrals, equipment, teaching, and transport still open. They rank as high when they block a discharge due within 24 hours or have waited 24 hours or more.</li>
          <li><b>Ownership:</b> every issue can be assigned to a role. Unassigned issues are counted, because an issue nobody owns is how things get dropped.</li>
          <li>This demo uses a rules engine on structured tags. A production version would use a language model to pull the same structured instructions out of free-text notes and orders.</li>
        </ul>
      </details>

      <SummaryTiles rows={rows} owners={state.owners} />

      <div className="grid">
        <PatientList rows={rows} />
        <Outlet context={{ rows, state, actions }} />
      </div>

      <p className="foot">
        All patients, notes, and organizations in this demo are invented. Baton is a coordination aid
        and does not replace clinical judgment or hospital policy.
      </p>

      {briefOpen && (
        <BriefModal text={briefText(PATIENTS, state)} onClose={() => setBriefOpen(false)} />
      )}
    </div>
  )
}

function SelectPrompt() {
  return (
    <main>
      <div className="empty">
        <b>Select a patient</b>
        The unit summary above counts every open issue on 4 West. Choose a patient to see what needs attention.
      </div>
    </main>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/patients" replace />} />
      <Route path="/patients" element={<Panel />}>
        <Route index element={<SelectPrompt />} />
        <Route path=":patientId" element={<PatientDetail />} />
      </Route>
      <Route path="*" element={<Navigate to="/patients" replace />} />
    </Routes>
  )
}
