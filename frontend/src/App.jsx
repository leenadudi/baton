import { useEffect, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export default function App() {
  const [apiStatus, setApiStatus] = useState('Checking API…')

  useEffect(() => {
    fetch(`${API_URL}/api/health`)
      .then((response) => {
        if (!response.ok) throw new Error('Health check failed')
        return response.json()
      })
      .then(({ message }) => setApiStatus(message))
      .catch(() => setApiStatus('API unavailable — start the FastAPI server.'))
  }, [])

  return (
    <main>
      <section>
        <p className="eyebrow">Baton</p>
        <h1>Your React + Python app is ready.</h1>
        <p className="description">
          Build the interface here and add API endpoints in <code>backend/app/main.py</code>.
        </p>
        <p className="status" role="status">{apiStatus}</p>
      </section>
    </main>
  )
}
