import { useEffect, useRef, useState } from 'react'

export default function BriefModal({ text, onClose, canPublish, onPublish }) {
  const [copied, setCopied] = useState('')
  const [published, setPublished] = useState(null) // { url } or { error }
  const ref = useRef(null)

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    // Move focus into the dialog, and hand it back to whatever opened it.
    const opener = document.activeElement
    ref.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      if (opener instanceof HTMLElement) opener.focus()
    }
  }, [onClose])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied('Copied')
    } catch {
      ref.current?.select()
      setCopied('Select the text and copy it manually')
    }
  }

  const publish = async () => {
    try {
      const res = await onPublish()
      setPublished({ url: res.url })
    } catch (e) {
      setPublished({ error: e.message })
    }
  }

  return (
    <div
      className="ov open" role="dialog" aria-modal="true" aria-labelledby="ovt"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="modal">
        <h2 id="ovt">Shift handoff brief</h2>
        <div className="tag">Open issues, most urgent first. Copy it into your handoff tool or read it aloud at huddle.</div>
        <textarea ref={ref} readOnly value={text} />
        <div className="row-act">
          <span className="tag" aria-live="polite">
            {copied}
            {published?.url && (
              <>
                {' '}Published —{' '}
                <a href={published.url} target="_blank" rel="noreferrer">View on FHIR server</a>
              </>
            )}
            {published?.error && ` Publish failed: ${published.error}`}
          </span>
          <button className="btn" onClick={copy}>Copy brief</button>
          {canPublish && (
            <button className="btn" onClick={publish} disabled={!!published?.url}>
              Publish to chart
            </button>
          )}
          <button className="btn primary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}
