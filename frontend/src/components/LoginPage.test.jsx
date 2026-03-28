import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect } from "vitest"
import LoginPage from "./LoginPage"

describe("LoginPage", () => {
  it("renders the app name", () => {
    render(<LoginPage />)
    expect(screen.getByText("RSS Reader")).toBeInTheDocument()
  })

  it("renders the sign in button", () => {
    render(<LoginPage />)
    expect(screen.getByRole("button", { name: /sign in with google/i })).toBeInTheDocument()
  })

  it("renders the tagline", () => {
    render(<LoginPage />)
    expect(screen.getByText(/your personal feed/i)).toBeInTheDocument()
  })

  it("clicking sign in redirects to backend auth URL", async () => {
    const user = userEvent.setup()
    // jsdom doesn't navigate, so capture the assignment
    const originalLocation = window.location
    delete window.location
    window.location = { href: "" }

    render(<LoginPage />)
    await user.click(screen.getByRole("button", { name: /sign in with google/i }))

    expect(window.location.href).toBe("http://localhost:8000/auth/login")

    window.location = originalLocation
  })
})
