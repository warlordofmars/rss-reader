import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Plus, RefreshCw, Trash2, Rss } from "lucide-react"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import AddFeedDialog from "./AddFeedDialog"

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
    <aside className="flex flex-col w-60 border-r bg-sidebar shrink-0">
      <div className="flex items-center justify-between px-4 py-3">
        <span className="text-sm font-medium text-sidebar-foreground">Feeds</span>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setDialogOpen(true)}>
          <Plus className="h-4 w-4" />
        </Button>
      </div>

      <ScrollArea className="flex-1">
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
            <span className="truncate flex-1 mr-1">{feed.title}</span>
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
    </aside>
  )
}
