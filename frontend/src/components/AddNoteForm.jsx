import { useRef, useState } from 'react'
import { ROLES, TOPICS } from '../data/chart.js'

const EMPTY = { role: ROLES[0], topic: '', value: '', text: '' }

export default function AddNoteForm({ pid, actions }) {
  const [form, setForm] = useState(EMPTY)
  const [hint, setHint] = useState('')
  const valueRef = useRef(null)
  const textRef = useRef(null)

  const set = (k) => (e) => {
    setHint('')
    setForm((f) => ({ ...f, [k]: e.target.value }))
  }

  // Prototype focuses the field that is blocking the add (prototype.html:617-618).
  // Say why as well, so a half-filled form cannot fail silently.
  const submit = () => {
    const text = form.text.trim()
    if (form.topic && !form.value) {
      setHint(`Choose which ${TOPICS[form.topic].label.toLowerCase()} instruction to add.`)
      valueRef.current?.focus()
      return
    }
    if (!form.topic && !text) {
      setHint('Pick a topic, or write a comment-only note.')
      textRef.current?.focus()
      return
    }
    actions.addNote(pid, { ...form, text })
    setForm(EMPTY)
    setHint('')
  }

  return (
    <>
      <h3 style={{ marginTop: 20, fontSize: 16 }}>Add an instruction</h3>
      <div className="tag">Try it: on David L., add Diet: NPO as Dietitian and watch a conflict appear.</div>
      <div className="form">
        <label>From role
          <select value={form.role} onChange={set('role')}>
            {ROLES.map((r) => <option key={r}>{r}</option>)}
          </select>
        </label>
        <label>Topic
          <select
            value={form.topic}
            onChange={(e) => { setHint(''); setForm((f) => ({ ...f, topic: e.target.value, value: '' })) }}
          >
            <option value="">Comment only</option>
            {Object.keys(TOPICS).map((k) => <option key={k} value={k}>{TOPICS[k].label}</option>)}
          </select>
        </label>
        <label>Instruction
          <select ref={valueRef} value={form.value} onChange={set('value')} disabled={!form.topic}>
            {form.topic
              ? [<option key="" value="">Choose instruction</option>,
                 ...TOPICS[form.topic].values.map((v) => <option key={v}>{v}</option>)]
              : <option value="">Choose a topic first</option>}
          </select>
        </label>
        <label className="wide">Note (optional)
          <input
            ref={textRef} type="text" placeholder="What did the team say or order?"
            value={form.text} onChange={set('text')}
          />
        </label>
        <div className="wide row-act">
          <button className="btn primary" onClick={submit}>Add to chart</button>
          <span className="tag" role="status" aria-live="polite">{hint}</span>
        </div>
      </div>
    </>
  )
}
