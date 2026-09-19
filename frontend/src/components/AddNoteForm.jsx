import { useState } from 'react'
import { ROLES, TOPICS } from '../data/chart.js'

const EMPTY = { role: ROLES[0], topic: '', value: '', text: '' }

export default function AddNoteForm({ pid, actions }) {
  const [form, setForm] = useState(EMPTY)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = () => {
    const text = form.text.trim()
    if (form.topic && !form.value) return
    if (!form.topic && !text) return
    actions.addNote(pid, { ...form, text })
    setForm(EMPTY)
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
            onChange={(e) => setForm((f) => ({ ...f, topic: e.target.value, value: '' }))}
          >
            <option value="">Comment only</option>
            {Object.keys(TOPICS).map((k) => <option key={k} value={k}>{TOPICS[k].label}</option>)}
          </select>
        </label>
        <label>Instruction
          <select value={form.value} onChange={set('value')} disabled={!form.topic}>
            {form.topic
              ? [<option key="" value="">Choose instruction</option>,
                 ...TOPICS[form.topic].values.map((v) => <option key={v}>{v}</option>)]
              : <option value="">Choose a topic first</option>}
          </select>
        </label>
        <label className="wide">Note (optional)
          <input
            type="text" placeholder="What did the team say or order?"
            value={form.text} onChange={set('text')}
          />
        </label>
        <div className="wide">
          <button className="btn primary" onClick={submit}>Add to chart</button>
        </div>
      </div>
    </>
  )
}
