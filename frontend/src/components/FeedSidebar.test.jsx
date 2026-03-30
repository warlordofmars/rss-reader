import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import FeedSidebar from "./FeedSidebar"
import { api } from "@/lib/api"

vi.mock("@/lib/api", () => ({
  api: {
    getFeeds: vi.fn(),
    deleteFeed: vi.fn(),
    refreshFeed: vi.fn(),
  },
}))

const healthyFeed = {
  id: "feed-1",
  title: "Healthy Feed",
  unread_count: 3,
  last_fetched_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(), // 10 min ago
  last_error: null,
}

const errorFeed = {
  id: "feed-2",
  title: "Broken Feed",
  unread_count: 0,
  last_fetched_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(), // 1 hr ago
  last_error: "Failed to fetch: connection refused",
}

const defaultProps = {
  selectedFeedId: null,
  onSelectFeed: vi.fn(),
  feeds: [healthyFeed, errorFeed],
  setFeeds: vi.fn(),
}

describe("FeedSidebar", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getFeeds.mockResolvedValue([])
  })

  it("renders feed titles", () => {
    render(<FeedSidebar {...defaultProps} />)
    expect(screen.getByText("Healthy Feed")).toBeInTheDocument()
    expect(screen.getByText("Broken Feed")).toBeInTheDocument()
  })

  it("renders AlertCircle icon for feeds with errors", () => {
    render(<FeedSidebar {...defaultProps} />)
    expect(document.querySelector('[data-feed-health="error"]')).not.toBeNull()
  })

  it("shows tooltip with error message on mouseenter for error feed", () => {
    render(<FeedSidebar {...defaultProps} />)
    const errorIcon = document.querySelector('[data-feed-health="error"]')
    expect(errorIcon).not.toBeNull()

    fireEvent.mouseEnter(errorIcon)

    expect(screen.getByText("Failed to fetch: connection refused")).toBeInTheDocument()
  })

  it("shows tooltip with last_fetched_at on mouseenter for healthy feed", () => {
    render(<FeedSidebar {...defaultProps} />)
    const healthIcon = document.querySelector('[data-feed-health="healthy"]')
    expect(healthIcon).not.toBeNull()

    fireEvent.mouseEnter(healthIcon)

    expect(screen.getByText(/Fetched:/)).toBeInTheDocument()
    expect(screen.getByText(/10m ago/)).toBeInTheDocument()
  })

  it("hides tooltip on mouseleave", () => {
    render(<FeedSidebar {...defaultProps} />)
    const errorIcon = document.querySelector('[data-feed-health="error"]')

    fireEvent.mouseEnter(errorIcon)
    expect(screen.getByText("Failed to fetch: connection refused")).toBeInTheDocument()

    fireEvent.mouseLeave(errorIcon)
    expect(screen.queryByText("Failed to fetch: connection refused")).not.toBeInTheDocument()
  })

  it("shows 'never' for feeds with no last_fetched_at", () => {
    const props = {
      ...defaultProps,
      feeds: [{ ...errorFeed, last_fetched_at: null }],
    }
    render(<FeedSidebar {...props} />)
    const errorIcon = document.querySelector('[data-feed-health="error"]')
    fireEvent.mouseEnter(errorIcon)
    expect(screen.getByText(/Fetched: never/)).toBeInTheDocument()
  })

  it("calls onSelectFeed when a feed row is clicked", async () => {
    render(<FeedSidebar {...defaultProps} />)
    fireEvent.click(screen.getByText("Healthy Feed"))
    expect(defaultProps.onSelectFeed).toHaveBeenCalledWith("feed-1")
  })

  it("calls api.deleteFeed when delete button is clicked", async () => {
    api.deleteFeed.mockResolvedValue({})
    render(<FeedSidebar {...defaultProps} />)

    // Hover to reveal delete button
    const feedRow = screen.getByText("Healthy Feed").closest(".group")
    fireEvent.mouseEnter(feedRow)

    // Click the last group-hover button in that row (delete is 2nd, after refresh)
    const rowButtons = Array.from(feedRow.querySelectorAll("button[class*='group-hover']"))
    fireEvent.click(rowButtons[rowButtons.length - 1])

    await waitFor(() => {
      expect(api.deleteFeed).toHaveBeenCalledWith("feed-1")
    })
  })
})
