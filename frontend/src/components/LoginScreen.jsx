import { useState } from 'react'

// Sign in to join the shared unit (actions are attributed and visible to the
// whole team), or continue as a guest for a private sandbox.
export default function LoginScreen({ onLogin, onRegister, onGuest }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await (mode === 'login'
        ? onLogin(email, password)
        : onRegister(email, password, name))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="wrap auth">
      <div className="brand auth-brand">
        <img className="mark" src="/logo.png" alt="Baton" />
        <div>
          <h1 className="sr-only">Baton</h1>
          <div className="tag">Find what falls between care team members before the patient does</div>
        </div>
      </div>

      <section className="panel auth-card">
        <h2>{mode === 'login' ? 'Sign in to 4 West' : 'Join the 4 West team'}</h2>
        <p className="tag">
          Signed-in clinicians share one unit view — every action is attributed
          and visible to the team. Guests get a private sandbox instead.
        </p>
        <form className="form" onSubmit={submit}>
          {mode === 'register' && (
            <input
              value={name} onChange={(e) => setName(e.target.value)}
              placeholder="Your name (e.g. Dr. Rivera)" required
              autoComplete="name"
            />
          )}
          <input
            type="email" value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder="Email" required autoComplete="email"
          />
          <input
            type="password" value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password (6+ characters)" required minLength={6}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          />
          {error && <div className="auth-err" role="alert">{error}</div>}
          <button className="btn primary" disabled={busy}>
            {mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>
        <div className="row-act">
          <button className="btn ghost" onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login')
            setError('')
          }}>
            {mode === 'login' ? 'Create an account' : 'Back to sign in'}
          </button>
          <button className="btn ghost" onClick={onGuest}>Continue as guest</button>
        </div>
      </section>

      <p className="foot">
        Demo accounts only — synthetic data, no PHI. Baton is a coordination aid
        and does not replace clinical judgment or hospital policy.
      </p>
    </div>
  )
}
