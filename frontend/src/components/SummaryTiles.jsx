// Reference-style KPI cards over Baton's real counts. The sub-line is a derived
// severity split, not a trend arrow: there is no prior period to compare against,
// and inventing one would be fabricated data on a clinical screen.
export default function SummaryTiles({ patients }) {
  const by = { conflict: 0, handoff: 0, blocker: 0 }
  const sev = { high: 0, med: 0, low: 0 }
  let total = 0

  patients.forEach((p) => {
    p.issues.forEach((i) => {
      by[i.type] = (by[i.type] || 0) + 1
      sev[i.sev]++
      total++
    })
  })

  const pct = (n) => (total ? (n / total) * 100 : 0)

  return (
    <section className="stats" aria-label="Unit summary">
      <div className="stat s-conflict">
        <div className="k">Conflicting instructions<span className="dot" style={{ background: 'var(--conflict)' }} /></div>
        <div className="v">{by.conflict}</div>
        <div className="note">Two or more active instructions on one topic</div>
      </div>

      <div className="stat s-handoff">
        <div className="k">Handoff gaps<span className="dot" style={{ background: 'var(--handoff)' }} /></div>
        <div className="v">{by.handoff}</div>
        <div className="note">Required fields empty, or results with no owner</div>
      </div>

      <div className="stat s-blocker">
        <div className="k">Administrative blockers<span className="dot" style={{ background: 'var(--blocker)' }} /></div>
        <div className="v">{by.blocker}</div>
        <div className="note">Authorisations, referrals, equipment, transport</div>
      </div>

      <div className="stat s-warn">
        <div className="k">Open issues by severity</div>
        <div className="v">{total}</div>
        <div className="seg" role="img"
          aria-label={`${sev.high} high, ${sev.med} medium, ${sev.low} low priority`}>
          <i style={{ width: `${pct(sev.high)}%`, background: 'var(--conflict)' }} />
          <i style={{ width: `${pct(sev.med)}%`, background: 'var(--handoff)' }} />
          <i style={{ width: `${pct(sev.low)}%`, background: 'var(--ok)' }} />
        </div>
        <div className="note">{sev.high} high · {sev.med} medium · {sev.low} low</div>
      </div>

    </section>
  )
}
