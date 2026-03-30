import { test as setup } from "@playwright/test"

const authFile = "e2e/.auth/user.json"
const apiURL = process.env.E2E_API_URL ?? "http://localhost:8000"
const adminEmail = process.env.E2E_ADMIN_EMAIL ?? "e2e@test.com"

setup("authenticate via dev-login", async ({ page }) => {
  const res = await page.request.post(`${apiURL}/auth/dev-login`, {
    data: { email: adminEmail, name: "E2E Test User" },
  })

  if (!res.ok()) {
    throw new Error(
      `dev-login failed (${res.status()}): ${await res.text()}. ` +
        "Ensure ALLOW_DEV_LOGIN=true is set on the server."
    )
  }

  const { token } = await res.json()

  // Navigate to app so we can set localStorage on the correct origin
  await page.goto("/")
  await page.evaluate((t) => {
    localStorage.setItem("token", t)
  }, token)

  // Save full browser storage state (localStorage + cookies)
  await page.context().storageState({ path: authFile })
})
