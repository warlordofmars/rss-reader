import { test, expect, request } from "@playwright/test"
import { getAuthHeaders, apiURL } from "./helpers.js"

// A real public feed we can use for tests
const TEST_FEED_URL = "https://feeds.bbci.co.uk/news/rss.xml"

test.describe("feeds", () => {
  // Wipe all feeds before each test so leftover state from previous runs can't interfere
  test.beforeEach(async () => {
    const headers = getAuthHeaders()
    const ctx = await request.newContext()
    const feedsRes = await ctx.get(`${apiURL}/feeds`, { headers })
    const feeds = await feedsRes.json()
    await Promise.all(feeds.map((feed) => ctx.delete(`${apiURL}/feeds/${feed.id}`, { headers })))
    await ctx.dispose()
  })

  test("add feed via dialog then see it in sidebar", async ({ page }) => {
    await page.goto("/")
    await expect(page.getByRole("complementary").getByRole("button", { name: "All Articles" })).toBeVisible()

    // Open add-feed dialog
    await page.getByRole("button", { name: "Add feed" }).click()
    await expect(page.getByRole("dialog")).toBeVisible()

    await page.getByPlaceholder("https://example.com/feed.xml").fill(TEST_FEED_URL)
    await page.getByRole("button", { name: "Add Feed" }).click()

    // Dialog closes and feed appears in sidebar
    await expect(page.getByRole("dialog")).not.toBeVisible()
    // Feed title comes from the RSS feed — wait up to 15s for backend to fetch it
    await expect(page.getByRole("complementary").getByText("BBC News")).toBeVisible({ timeout: 15_000 })
  })

  test("adding a duplicate feed shows error", async ({ page }) => {
    // Pre-add the feed via API
    const headers = getAuthHeaders()
    const ctx = await request.newContext()
    await ctx.post(`${apiURL}/feeds`, { headers, data: { url: TEST_FEED_URL } })
    await ctx.dispose()

    await page.goto("/")

    await page.getByRole("button", { name: "Add feed" }).click()
    await page.getByPlaceholder("https://example.com/feed.xml").fill(TEST_FEED_URL)
    await page.getByRole("button", { name: "Add Feed" }).click()

    await expect(page.getByText("Feed already added.")).toBeVisible()
  })

  test("delete feed via group-hover button removes it from sidebar", async ({ page }) => {
    // Pre-add the feed via API
    const headers = getAuthHeaders()
    const ctx = await request.newContext()
    const res = await ctx.post(`${apiURL}/feeds`, { headers, data: { url: TEST_FEED_URL } })
    await ctx.dispose()

    await page.goto("/")
    const feedRow = page.getByRole("complementary").locator(".group", { hasText: "BBC News" })
    await expect(feedRow).toBeVisible({ timeout: 15_000 })

    // Hover the row to reveal the delete button
    await feedRow.hover()
    await feedRow.locator("button").last().click()

    await expect(page.getByRole("complementary").getByText("BBC News")).not.toBeVisible()
  })
})
