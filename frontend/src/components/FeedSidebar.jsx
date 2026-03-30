import { useEffect, useRef, useState } from "react"
import ReactDOM from "react-dom"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Plus, RefreshCw, Trash2, Rss, AlertCircle, CheckCircle2 } from "lucide-react"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import AddFeedDialog from "./AddFeedDialog"

function formatRelativeTime(isoString) {
  if (!isoString) return "never"
  const diff = Date.now() - new Date(isoString).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return "just now"
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function FeedHealthIcon({ feed }) {
  const [visible, setVisible] = useState(false)
  const [coords, setCoords] = useState({ top: 0, left: 0 })
  const triggerRef = useRef(null)

  const show = () => {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (rect) {
      setCoords({ top: rect.top + rect.height / 2, left: rect.right + 12 })
    }
    setVisible(true)
  }

  const hide = () => setVisible(false)

  return (
    <>
      <span
        ref={triggerRef}
        onMouseEnter={show}
        onMouseLeave={hide}
        data-feed-health={feed.last_error ? "error" : "healthy"}
        className="inline-flex shrink-0 cursor-default"
      >
        {feed.last_error ? (
          <AlertCircle className="h-3 w-3 text-destructive" />
        ) : (
          <CheckCircle2 className="h-3 w-3 text-muted-foreground/30 transition-colors group-hover:text-muted-foreground/60" />
        )}
      </span>

      {visible && ReactDOM.createPortal(
        <div
          className="fixed z-50 max-w-56 rounded-md bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md ring-1 ring-foreground/10 pointer-events-none space-y-1"
          style={{ top: coords.top, left: coords.left, transform: "translateY(-50%)" }}
        >
          {feed.last_error && (
            <p className="text-destructive font-medium break-words">{feed.last_error}</p>
          )}
          <p className="text-muted-foreground">
            Fetched: {formatRelativeTime(feed.last_fetched_at)}
          </p>
        </div>,
        document.body
      )}
    </>
  )
}

export default function FeedSidebar({ selectedFeedId, onSelectFeed, feeds, setFeeds }) {
  const [dialogOpen, setDialogOpen] = useState(false)

  useEffect(() => {
    api.getFeeds().then(setFeeds).catch(console.error)
  }, [setFeeds])

  const handleFeedAdded = (feed) => {
    setFeeds((prev) => [...prev, { ...feed, unread_count: 0 }])
    onSelectFeed(feed.id)
    // Reload after a moment to pick up unread_count from fetch
    setTimeout(() => api.getFeeds().then(setFeeds).catch(console.error), 3000)
  }

  const handleDelete = async (e, feedId) => {
    e.stopPropagation()
    await api.deleteFeed(feedId)
    setFeeds((prev) => prev.filter((f) => f.id !== feedId))
    if (selectedFeedId === feedId) onSelectFeed(null)
  }

  const handleRefresh = async (e, feedId) => {
    e.stopPropagation()
    await api.refreshFeed(feedId)
    setTimeout(() => api.getFeeds().then(setFeeds).catch(console.error), 3000)
  }

  const totalUnread = feeds.reduce((sum, f) => sum + (f.unread_count || 0), 0)

  return (
    <aside className="flex flex-col w-60 border-r bg-sidebar shrink-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 shrink-0">
        <span className="text-sm font-medium text-sidebar-foreground">Feeds</span>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setDialogOpen(true)}>
          <Plus className="h-4 w-4" />
        </Button>
      </div>

      <ScrollArea className="flex-1 min-h-0">
        {/* All Articles */}
        <button
          onClick={() => onSelectFeed(null)}
          className={cn(
            "flex items-center justify-between w-full px-4 py-2 text-sm hover:bg-sidebar-accent transition-colors",
            selectedFeedId === null && "bg-sidebar-accent font-medium"
          )}
        >
          <span className="flex items-center gap-2">
            <Rss className="h-3.5 w-3.5 text-muted-foreground" />
            All Articles
          </span>
          {totalUnread > 0 && (
            <Badge variant="secondary" className="text-xs h-5 px-1.5">
              {totalUnread}
            </Badge>
          )}
        </button>

        <Separator className="my-1" />

        {feeds.map((feed) => (
          <div
            key={feed.id}
            onClick={() => onSelectFeed(feed.id)}
            className={cn(
              "group flex items-center justify-between px-4 py-2 cursor-pointer text-sm hover:bg-sidebar-accent transition-colors",
              selectedFeedId === feed.id && "bg-sidebar-accent font-medium"
            )}
          >
            <span className="truncate flex-1 mr-1 flex items-center gap-1.5">
              <FeedHealthIcon feed={feed} />
              {feed.title}
            </span>
            <div className="flex items-center gap-1">
              {feed.unread_count > 0 && (
                <Badge variant="secondary" className="text-xs h-5 px-1.5">
                  {feed.unread_count}
                </Badge>
              )}
              <button
                onClick={(e) => handleRefresh(e, feed.id)}
                className="hidden group-hover:flex items-center text-muted-foreground hover:text-foreground"
              >
                <RefreshCw className="h-3 w-3" />
              </button>
              <button
                onClick={(e) => handleDelete(e, feed.id)}
                className="hidden group-hover:flex items-center text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          </div>
        ))}
      </ScrollArea>

      <AddFeedDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onFeedAdded={handleFeedAdded}
      />

      <div className="px-4 py-2 border-t">
        <span className="text-xs text-muted-foreground">
          v{import.meta.env.VITE_APP_VERSION ?? "dev"}
        </span>
      </div>
    </aside>
  )
}
