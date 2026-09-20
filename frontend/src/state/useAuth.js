// Signed-in clinician, backed by the bearer token in localStorage.
// doctor === undefined means "still checking", null means guest.
import { useCallback, useEffect, useState } from 'react'
import { api, getToken, setToken } from '../api.js'

export function useAuth() {
  const [doctor, setDoctor] = useState(undefined)

  useEffect(() => {
    if (!getToken()) { setDoctor(null); return }
    api.me()
      .then(setDoctor)
      .catch(() => { setToken(null); setDoctor(null) })
  }, [])

  const finish = useCallback(({ token, doctor: d }) => {
    setToken(token)
    setDoctor(d)
  }, [])

  const login = useCallback(
    (email, password) => api.login(email, password).then(finish), [finish])
  const register = useCallback(
    (email, password, name) => api.register(email, password, name).then(finish),
    [finish])
  const logout = useCallback(() => {
    api.logout().catch(() => {})
    setToken(null)
    setDoctor(null)
  }, [])

  return { doctor, login, register, logout }
}
