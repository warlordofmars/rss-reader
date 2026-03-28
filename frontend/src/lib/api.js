const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000"

function getToken() {
  return localStorage.getItem("token")
}

async function apiFetch(path, options = {}) {
  const token = getToken()
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  getMe: () => apiFetch("/auth/me"),

  getFeeds: () => apiFetch("/feeds"),
  addFeed: (url) =>
    apiFetch("/feeds", { method: "POST", body: JSON.stringify({ url }) }),
  deleteFeed: (id) => apiFetch(`/feeds/${id}`, { method: "DELETE" }),
  refreshFeed: (id) => apiFetch(`/feeds/${id}/refresh`, { method: "POST" }),

  getArticles: ({ feedId, keyword, unreadOnly, cursor } = {}) => {
    const q = new URLSearchParams()
    if (feedId) q.set("feed_id", feedId)
    if (keyword) q.set("keyword", keyword)
    if (unreadOnly) q.set("unread_only", "true")
    if (cursor) q.set("cursor", cursor)
    return apiFetch(`/articles?${q}`)
  },
  markRead: (id) => apiFetch(`/articles/${id}/read`, { method: "PATCH" }),
  markUnread: (id) => apiFetch(`/articles/${id}/unread`, { method: "PATCH" }),
}
