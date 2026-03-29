import { useEffect, useState } from "react"
import { api } from "./lib/api"
import LoginPage from "./components/LoginPage"
import Layout from "./components/Layout"
import AdminPage from "./components/AdminPage"

export default function App() {
  if (window.location.pathname === "/admin") return <AdminPage />
  const [token, setToken] = useState(null)
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  // Pick up token from URL after Google OAuth redirect
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const urlToken = params.get("token")
    if (urlToken) {
      localStorage.setItem("token", urlToken)
      window.history.replaceState({}, "", "/")
      setToken(urlToken) // eslint-disable-line react-hooks/set-state-in-effect
    } else {
      const stored = localStorage.getItem("token")
      if (stored) setToken(stored)
      else setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!token) return
    api
      .getMe()
      .then(setUser)
      .catch(() => {
        localStorage.removeItem("token")
        setToken(null)
      })
      .finally(() => setLoading(false))
  }, [token])

  const logout = () => {
    localStorage.removeItem("token")
    setToken(null)
    setUser(null)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen text-muted-foreground">
        Loading…
      </div>
    )
  }

  if (!user) return <LoginPage />
  return <Layout user={user} onLogout={logout} />
}
