import { describe, it, expect, vi, beforeEach } from "vitest"
import { api } from "./api"

const mockFetch = vi.fn()
vi.stubGlobal("fetch", mockFetch)

// Provide a simple localStorage mock
const store = {}
vi.stubGlobal("localStorage", {
  getItem: (k) => store[k] ?? null,
  setItem: (k, v) => { store[k] = v },
  removeItem: (k) => { delete store[k] },
  clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
})

function mockResponse(body, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  })
}

describe("api", () => {
  beforeEach(() => {
    mockFetch.mockReset()
    localStorage.clear()
  })

  it("getMe sends Authorization header when token is stored", async () => {
    localStorage.setItem("token", "my-jwt-token")
    mockFetch.mockReturnValue(mockResponse({ id: 1, email: "test@example.com" }))

    await api.getMe()

    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/auth/me",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer my-jwt-token" }),
      })
    )
  })

  it("getMe sends no Authorization header when no token", async () => {
    mockFetch.mockReturnValue(mockResponse({ id: 1 }))

    await api.getMe()

    const headers = mockFetch.mock.calls[0][1].headers
    expect(headers).not.toHaveProperty("Authorization")
  })

  it("addFeed posts correct body", async () => {
    localStorage.setItem("token", "tok")
    mockFetch.mockReturnValue(mockResponse({ id: 1, url: "https://example.com/rss" }, 201))

    await api.addFeed("https://example.com/rss")

    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/feeds",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ url: "https://example.com/rss" }),
      })
    )
  })

  it("deleteFeed sends DELETE request", async () => {
    localStorage.setItem("token", "tok")
    mockFetch.mockReturnValue(mockResponse(null, 204))

    await api.deleteFeed(42)

    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/feeds/42",
      expect.objectContaining({ method: "DELETE" })
    )
  })

  it("getArticles builds query string correctly", async () => {
    localStorage.setItem("token", "tok")
    mockFetch.mockReturnValue(mockResponse([]))

    await api.getArticles({ feedId: 5, keyword: "python", unreadOnly: true })

    const url = mockFetch.mock.calls[0][0]
    expect(url).toContain("feed_id=5")
    expect(url).toContain("keyword=python")
    expect(url).toContain("unread_only=true")
  })

  it("getArticles with no params fetches all articles", async () => {
    localStorage.setItem("token", "tok")
    mockFetch.mockReturnValue(mockResponse([]))

    await api.getArticles()

    const url = mockFetch.mock.calls[0][0]
    expect(url).toBe("http://localhost:8000/articles?")
  })

  it("refreshFeed sends POST request", async () => {
    localStorage.setItem("token", "tok")
    mockFetch.mockReturnValue(mockResponse({ status: "refreshing" }))

    await api.refreshFeed(7)

    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/feeds/7/refresh",
      expect.objectContaining({ method: "POST" })
    )
  })

  it("markRead sends PATCH to read endpoint", async () => {
    localStorage.setItem("token", "tok")
    mockFetch.mockReturnValue(mockResponse({ id: 3, is_read: true }))

    await api.markRead(3)

    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/articles/3/read",
      expect.objectContaining({ method: "PATCH" })
    )
  })

  it("markUnread sends PATCH to unread endpoint", async () => {
    localStorage.setItem("token", "tok")
    mockFetch.mockReturnValue(mockResponse({ id: 3, is_read: false }))

    await api.markUnread(3)

    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/articles/3/unread",
      expect.objectContaining({ method: "PATCH" })
    )
  })

  it("throws on non-ok response", async () => {
    localStorage.setItem("token", "tok")
    mockFetch.mockReturnValue(mockResponse({ detail: "Not found" }, 404))

    await expect(api.getFeeds()).rejects.toThrow("API error: 404")
  })
})
