import fs from "fs"

const authFile = "e2e/.auth/user.json"
export const apiURL = process.env.E2E_API_URL ?? "http://localhost:8000"

/**
 * Read the JWT from the saved storageState and return fetch-compatible headers.
 */
export function getAuthHeaders() {
  const state = JSON.parse(fs.readFileSync(authFile, "utf8"))
  const origin = process.env.E2E_FRONTEND_URL ?? "http://localhost:5173"
  const entry = state.origins
    ?.find((o) => o.origin === origin)
    ?.localStorage?.find((e) => e.name === "token")
  if (!entry) throw new Error("No token found in storageState — did auth.setup run?")
  return { Authorization: `Bearer ${entry.value}` }
}
