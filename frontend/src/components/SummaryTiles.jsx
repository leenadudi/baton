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
  const open = conflict + handoff + blocker

  const stats = [
    ['conflict', conflict, 'Conflicting instructions'],
    ['handoff', handoff, 'Handoff gaps'],
    ['blocker', blocker, 'Stuck blockers'],
    ['warn', unowned, 'Nobody owns'],
    ['warn', atRisk, 'Discharge at risk <24h'],
  ]

  return (
    <section className="strip" aria-label="Unit summary">
      <div className="strip-lead">
        <div className="n">{open}</div>
        <div className="l">open issues across<br />{patients.length} patients</div>
      </div>
      {stats.map(([cls, n, label]) => (
        <div className={`stat ${cls}`} key={label}>
          <div className="n">{n}</div>
          <div className="l">{label}</div>
        </div>
      ))}
    </section>
  )
}
