export default function SummaryTiles({ patients }) {
  let conflict = 0, handoff = 0, blocker = 0, unowned = 0, atRisk = 0
  patients.forEach((p) => {
    p.issues.forEach((i) => {
      if (i.type === 'conflict') conflict++
      else if (i.type === 'handoff') handoff++
      else blocker++
      if (!i.owner) unowned++
    })
    if (p.dischargeInH <= 24 && p.dischStatus === 'risk') atRisk++
  })

  const tiles = [
    ['t-conflict', conflict, 'Conflicting instructions'],
    ['t-handoff', handoff, 'Handoff gaps'],
    ['t-blocker', blocker, 'Administrative blockers'],
    ['t-warn', unowned, 'Issues with no owner'],
    ['t-warn', atRisk, 'Discharges due within 24h that are at risk'],
  ]

  return (
    <section className="tiles" aria-label="Unit summary">
      {tiles.map(([cls, n, label]) => (
        <div className={`tile ${cls}`} key={label}>
          <div className="n">{n}</div>
          <div className="l">{label}</div>
        </div>
      ))}
    </section>
  )
}
