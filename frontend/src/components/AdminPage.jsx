import { useEffect, useState } from "react"

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000"

function adminFetch(path, credentials) {
  const encoded = btoa(`${credentials.username}:${credentials.password}`)
  return fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Basic ${encoded}` },
  }).then((res) => {
    if (res.status === 401) throw new Error("unauthorized")
    if (!res.ok) throw new Error(`API error: ${res.status}`)
    return res.json()
  })
}

function LoginForm({ onLogin, error }) {
  const [username, setUsername] = useState("admin")
  const [password, setPassword] = useState("")

  const submit = (e) => {
    e.preventDefault()
    onLogin({ username, password })
  }

  return (
    <div className="flex items-center justify-center h-screen bg-background">
      <div className="w-full max-w-sm p-8 border rounded-lg shadow-sm">
        <h1 className="text-xl font-semibold mb-6">Admin Login</h1>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Username</label>
            <input
              className="w-full border rounded px-3 py-2 text-sm bg-background"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Password</label>
            <input
              type="password"
              className="w-full border rounded px-3 py-2 text-sm bg-background"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <button
            type="submit"
            className="w-full bg-primary text-primary-foreground rounded px-3 py-2 text-sm font-medium hover:bg-primary/90"
          >
            Sign in
          </button>
        </form>
      </div>
    </div>
  )
}

function UserRow({ user, onSelect, selected }) {
  return (
    <tr
      className={`border-b cursor-pointer hover:bg-muted/50 transition-colors ${selected ? "bg-muted" : ""}`}
      onClick={() => onSelect(user)}
    >
      <td className="py-3 px-4">
        <div className="flex items-center gap-3">
          {user.picture && (
            <img src={user.picture} alt="" className="w-7 h-7 rounded-full" />
          )}
          <div>
            <div className="font-medium text-sm">{user.name}</div>
            <div className="text-xs text-muted-foreground">{user.email}</div>
          </div>
        </div>
      </td>
      <td className="py-3 px-4 text-sm text-center">{user.feed_count}</td>
      <td className="py-3 px-4 text-sm text-center">{user.article_count}</td>
      <td className="py-3 px-4 text-sm text-center">{user.total_unread}</td>
      <td className="py-3 px-4 text-xs text-muted-foreground">
        {user.created_at ? new Date(user.created_at).toLocaleDateString() : "—"}
      </td>
    </tr>
  )
}

function UserDetail({ user, onClose }) {
  return (
    <div className="border-l h-full overflow-y-auto p-6">
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-3">
          {user.picture && (
            <img src={user.picture} alt="" className="w-12 h-12 rounded-full" />
          )}
          <div>
            <div className="font-semibold">{user.name}</div>
            <div className="text-sm text-muted-foreground">{user.email}</div>
          </div>
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-lg leading-none">✕</button>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: "Feeds", value: user.feed_count },
          { label: "Articles", value: user.article_count },
          { label: "Unread", value: user.total_unread },
        ].map(({ label, value }) => (
          <div key={label} className="border rounded p-3 text-center">
            <div className="text-2xl font-bold">{value}</div>
            <div className="text-xs text-muted-foreground mt-1">{label}</div>
          </div>
        ))}
      </div>

      <div className="text-xs text-muted-foreground mb-4">
        Joined {user.created_at ? new Date(user.created_at).toLocaleString() : "—"}
      </div>

      {user.feeds?.length > 0 && (
        <>
          <h3 className="text-sm font-semibold mb-3">Feeds</h3>
          <div className="space-y-2">
            {user.feeds.map((f) => (
              <div key={f.feed_id} className="flex items-center justify-between text-sm border rounded px-3 py-2">
                <span className="truncate text-muted-foreground flex-1 mr-2">{f.title || f.feed_id}</span>
                <span className="text-xs shrink-0">{f.unread_count} unread</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export default function AdminPage() {
  const [credentials, setCredentials] = useState(null)
  const [loginError, setLoginError] = useState(null)
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedUser, setSelectedUser] = useState(null)
  const [infra, setInfra] = useState({})

  const login = (creds) => {
    setLoading(true)
    setLoginError(null)
    adminFetch("/admin/users", creds)
      .then((data) => {
        setCredentials(creds)
        setUsers(data)
      })
      .catch((err) => {
        setLoginError(err.message === "unauthorized" ? "Invalid credentials" : "Login failed")
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!credentials) return
    adminFetch("/admin/users", credentials)
      .then(setUsers)
      .catch(() => setCredentials(null))
    adminFetch("/admin/infra", credentials)
      .then(setInfra)
      .catch(() => {})
  }, [credentials])

  if (!credentials) {
    return <LoginForm onLogin={login} error={loginError} />
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen text-muted-foreground">
        Loading…
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen bg-background">
      <header className="border-b px-6 py-3 flex items-center justify-between shrink-0">
        <h1 className="font-semibold">Admin — Users ({users.length})</h1>
        <div className="flex items-center gap-4">
          {infra.dashboard && (
            <a
              href={infra.dashboard}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              CloudWatch Dashboard ↗
            </a>
          )}
          {infra.lambda_logs && (
            <a
              href={infra.lambda_logs}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              Lambda Logs ↗
            </a>
          )}
          <button
            onClick={() => setCredentials(null)}
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            Sign out
          </button>
        </div>
      </header>

      <div className="flex flex-1 min-h-0">
        <div className={`flex-1 overflow-auto ${selectedUser ? "hidden md:block" : ""}`}>
          <table className="w-full text-left">
            <thead className="border-b bg-muted/30">
              <tr>
                <th className="py-3 px-4 text-xs font-medium text-muted-foreground">User</th>
                <th className="py-3 px-4 text-xs font-medium text-muted-foreground text-center">Feeds</th>
                <th className="py-3 px-4 text-xs font-medium text-muted-foreground text-center">Articles</th>
                <th className="py-3 px-4 text-xs font-medium text-muted-foreground text-center">Unread</th>
                <th className="py-3 px-4 text-xs font-medium text-muted-foreground">Joined</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <UserRow
                  key={u.google_id}
                  user={u}
                  selected={selectedUser?.google_id === u.google_id}
                  onSelect={setSelectedUser}
                />
              ))}
              {users.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-12 text-center text-sm text-muted-foreground">
                    No users yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {selectedUser && (
          <div className="w-80 shrink-0">
            <UserDetail user={selectedUser} onClose={() => setSelectedUser(null)} />
          </div>
        )}
      </div>
    </div>
  )
}
