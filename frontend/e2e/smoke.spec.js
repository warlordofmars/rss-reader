import { test, expect } from "@playwright/test"

test.describe("smoke", () => {
  test("app loads and shows main layout for authenticated user", async ({ page }) => {
    await page.goto("/")
    // The sidebar "All Articles" button is the reliable auth-gated element
    await expect(page.getByRole("complementary").getByRole("button", { name: "All Articles" })).toBeVisible()
  })

  test("shows user name in header", async ({ page }) => {
    await page.goto("/")
    await expect(page.getByText("E2E Test User")).toBeVisible()
  })

  test("unauthenticated user sees login page", async ({ page }) => {
    await page.goto("/")
    // Clear the stored token then reload — app should fall through to LoginPage
    await page.evaluate(() => localStorage.clear())
    await page.reload()
    await expect(page.getByText("Sign in with Google")).toBeVisible()
  })
})
