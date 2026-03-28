import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, it, expect, vi, beforeEach } from "vitest"
import AddFeedDialog from "./AddFeedDialog"
import { api } from "@/lib/api"

vi.mock("@/lib/api", () => ({
  api: {
    addFeed: vi.fn(),
  },
}))

const defaultProps = {
  open: true,
  onOpenChange: vi.fn(),
  onFeedAdded: vi.fn(),
}

describe("AddFeedDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("renders the dialog when open", () => {
    render(<AddFeedDialog {...defaultProps} />)
    expect(screen.getByRole("heading", { name: /add feed/i })).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/https:\/\/example.com/i)).toBeInTheDocument()
  })

  it("submit button is disabled when URL is empty", () => {
    render(<AddFeedDialog {...defaultProps} />)
    expect(screen.getByRole("button", { name: /add feed/i })).toBeDisabled()
  })

  it("submit button enables when URL is entered", async () => {
    const user = userEvent.setup()
    render(<AddFeedDialog {...defaultProps} />)

    await user.type(screen.getByPlaceholderText(/https:\/\/example.com/i), "https://blog.com/rss")
    expect(screen.getByRole("button", { name: /add feed/i })).toBeEnabled()
  })

  it("calls api.addFeed and onFeedAdded on successful submit", async () => {
    const user = userEvent.setup()
    const newFeed = { id: 1, url: "https://blog.com/rss", title: "My Blog" }
    api.addFeed.mockResolvedValue(newFeed)

    render(<AddFeedDialog {...defaultProps} />)
    await user.type(screen.getByPlaceholderText(/https:\/\/example.com/i), "https://blog.com/rss")
    await user.click(screen.getByRole("button", { name: /add feed/i }))

    await waitFor(() => {
      expect(api.addFeed).toHaveBeenCalledWith("https://blog.com/rss")
      expect(defaultProps.onFeedAdded).toHaveBeenCalledWith(newFeed)
      expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
    })
  })

  it("shows error message on duplicate feed", async () => {
    const user = userEvent.setup()
    api.addFeed.mockRejectedValue(new Error("API error: 409"))

    render(<AddFeedDialog {...defaultProps} />)
    await user.type(screen.getByPlaceholderText(/https:\/\/example.com/i), "https://blog.com/rss")
    await user.click(screen.getByRole("button", { name: /add feed/i }))

    await waitFor(() => {
      expect(screen.getByText("Feed already added.")).toBeInTheDocument()
    })
  })

  it("shows generic error on other failures", async () => {
    const user = userEvent.setup()
    api.addFeed.mockRejectedValue(new Error("API error: 500"))

    render(<AddFeedDialog {...defaultProps} />)
    await user.type(screen.getByPlaceholderText(/https:\/\/example.com/i), "https://blog.com/rss")
    await user.click(screen.getByRole("button", { name: /add feed/i }))

    await waitFor(() => {
      expect(screen.getByText("Failed to add feed.")).toBeInTheDocument()
    })
  })

  it("cancel button closes the dialog", async () => {
    const user = userEvent.setup()
    render(<AddFeedDialog {...defaultProps} />)

    await user.click(screen.getByRole("button", { name: /cancel/i }))
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
  })
})
