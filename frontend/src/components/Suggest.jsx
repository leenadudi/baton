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
    setData(null)
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

export function SuggestBox({ children, onDismiss, label = 'Baton suggests' }) {
  return (
    <div className="suggest">
      <div className="suggest-head">
        <span className="suggest-tag"><Spark /> {label} <em>· advisory, you decide</em></span>
        {onDismiss && <button className="btn ghost small" onClick={onDismiss}>Dismiss</button>}
      </div>
      {children}
    </div>
  )
}

export function Spark() {
  return (
    <svg className="spark" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M8 1l1.6 4.4L14 7l-4.4 1.6L8 13 6.4 8.6 2 7l4.4-1.6z" fill="currentColor" />
    </svg>
  )
}

// Quiet, link-style trigger for an on-demand suggestion.
export function SuggestButton({ loading, onClick, children }) {
  return (
    <button className="sbtn" disabled={loading} onClick={onClick}>
      <Spark /> {loading ? 'Thinking…' : children}
    </button>
  )
}
