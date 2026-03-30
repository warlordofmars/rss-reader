import { test, expect, request } from "@playwright/test"
import { getAuthHeaders, apiURL } from "./helpers.js"

const TEST_FEED_URL = "https://feeds.bbci.co.uk/news/rss.xml"

test.describe("feed health tooltip", () => {
  test.beforeAll(async () => {
    // Ensure the test feed exists (idempotent — 409 is fine)
    const headers = getAuthHeaders()
    const ctx = await request.newContext()
    await ctx.post(`${apiURL}/feeds`, { headers, data: { url: TEST_FEED_URL } })
    await ctx.dispose()
  })

  test.afterAll(async () => {
    const headers = getAuthHeaders()
    const ctx = await request.newContext()
    const feedsRes = await ctx.get(`${apiURL}/feeds`, { headers })
    const feeds = await feedsRes.json()
    await Promise.all(feeds.map((feed) => ctx.delete(`${apiURL}/feeds/${feed.id}`, { headers })))
    await ctx.dispose()
  })

  test("hovering healthy icon shows Fetched timestamp tooltip", async ({ page }) => {
    await page.goto("/")
    await expect(page.locator('[data-feed-health="healthy"]').first()).toBeVisible({ timeout: 15_000 })

    await page.locator('[data-feed-health="healthy"]').first().hover()
    await expect(page.getByText(/Fetched:/)).toBeVisible()
  })

  test("tooltip disappears on mouse leave", async ({ page }) => {
    await page.goto("/")
    await expect(page.locator('[data-feed-health="healthy"]').first()).toBeVisible({ timeout: 15_000 })

    const icon = page.locator('[data-feed-health="healthy"]').first()
    await icon.hover()
    await expect(page.getByText(/Fetched:/)).toBeVisible()

    await page.mouse.move(0, 0)
    await expect(page.getByText(/Fetched:/)).not.toBeVisible()
  })

  test("error icon shows error message in tooltip", async ({ page }) => {
    // Set up route intercept BEFORE navigating so it catches the initial /feeds call
    await page.route(`${apiURL}/feeds`, async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue()
        return
      }
      const res = await route.fetch()
      const feeds = await res.json()
      feeds.push({
        id: "synthetic-error-feed",
        title: "Broken Test Feed",
        url: "https://broken.example.com/feed.xml",
        unread_count: 0,
        last_fetched_at: new Date(Date.now() - 3_600_000).toISOString(),
        last_error: "Connection refused: synthetic test error",
      })
      await route.fulfill({ json: feeds })
    })

    await page.goto("/")
    await expect(page.locator('[data-feed-health="error"]')).toBeVisible({ timeout: 15_000 })

    await page.locator('[data-feed-health="error"]').hover()
    await expect(page.getByText("Connection refused: synthetic test error")).toBeVisible()
    await expect(page.getByText(/Fetched:/)).toBeVisible()
  })
})
