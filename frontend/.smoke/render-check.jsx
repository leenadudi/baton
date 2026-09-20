// Renders the components that actually broke, with real fixture data.
// `vite build` only proves the bundle parses; this proves it runs.
import { renderToString } from 'react-dom/server'
import { StaticRouter } from 'react-router'
import PatientList from '../src/components/PatientList.jsx'
import SummaryTiles from '../src/components/SummaryTiles.jsx'
import { PATIENTS } from '../src/data/chart.js'
import { getIssues, riskOf, dischStatus } from '../src/lib/rules.js'

const st = { added:{}, filled:{}, cleared:{}, escalated:{}, pendOwners:{}, owners:{}, log:{}, nextSeq:1000 }
const patients = PATIENTS.map((p) => {
  const issues = getIssues(p, st).map((i) => ({ ...i, owner: st.owners[i.id] || null }))
  return { ...p, issues, risk: riskOf(issues), dischStatus: dischStatus(p, issues), log: [], notes: p.notes }
})

const cases = [
  ['PatientList', <PatientList patients={patients} query="" />],
  ['SummaryTiles', <SummaryTiles patients={patients} />],
  ['PatientList (empty)', <PatientList patients={[]} query="" />],
]

let failed = 0
for (const [label, el] of cases) {
  try {
    const html = renderToString(<StaticRouter location="/patients">{el}</StaticRouter>)
    if (!html.length) throw new Error('rendered empty')
    console.log(`  PASS  ${label} (${html.length} chars)`)
  } catch (e) {
    failed++
    console.log(`  FAIL  ${label}: ${e.message}`)
  }
}
console.log(failed ? `\n${failed} render failure(s)` : '\nall render checks passed')
process.exit(failed ? 1 : 0)
