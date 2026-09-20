import { useState } from 'react'

// One-shot advisory call behind a button. Suggestions are drafts — nothing is
// applied without the clinician acting on it through the normal controls.
export function useSuggestion(fn) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const run = async (...args) => {
    setLoading(true)
    setError(null)
    try {
      setData(await fn(...args))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }
  const clear = () => { setData(null); setError(null) }
  return { data, error, loading, run, clear }
}

export function SuggestBox({ children, onDismiss }) {
  return (
    <div className="suggest">
      <div className="suggest-head">
        <span className="suggest-tag">AI suggestion — review before using</span>
        <button className="btn ghost" onClick={onDismiss}>Dismiss</button>
      </div>
      {children}
    </div>
  )
}
