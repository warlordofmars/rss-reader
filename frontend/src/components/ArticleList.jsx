import { useEffect, useState } from "react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Search } from "lucide-react"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"

function formatDate(iso) {
  if (!iso) return ""
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
}

export default function ArticleList({
  selectedFeedId,
  feeds,
  selectedArticle,
  onSelectArticle,
  onArticlesLoaded,
}) {
  const [articles, setArticles] = useState([])
  const [keyword, setKeyword] = useState("")
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    api
      .getArticles({ feedId: selectedFeedId, keyword, unreadOnly })
      .then((data) => {
        setArticles(data)
        onArticlesLoaded?.(data)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [selectedFeedId, keyword, unreadOnly])

  const handleSelect = (article) => {
    onSelectArticle(article)
    if (!article.is_read) {
      api.markRead(article.id).catch(console.error)
      setArticles((prev) =>
        prev.map((a) => (a.id === article.id ? { ...a, is_read: true } : a))
      )
    }
  }

  const feedTitle = selectedFeedId
    ? feeds.find((f) => f.id === selectedFeedId)?.title ?? "Feed"
    : "All Articles"

  return (
    <div className="flex flex-col w-80 border-r shrink-0">
      {/* Header */}
      <div className="px-4 py-3 border-b space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium truncate">{feedTitle}</span>
          <Button
            variant={unreadOnly ? "secondary" : "ghost"}
            size="sm"
            className="text-xs h-7"
            onClick={() => setUnreadOnly((v) => !v)}
          >
            Unread
          </Button>
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            className="pl-8 h-8 text-sm"
            placeholder="Filter…"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>
      </div>

      <ScrollArea className="flex-1">
        {loading && (
          <p className="text-sm text-muted-foreground text-center py-8">Loading…</p>
        )}
        {!loading && articles.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-8">No articles found.</p>
        )}
        {articles.map((article) => (
          <button
            key={article.id}
            onClick={() => handleSelect(article)}
            className={cn(
              "w-full text-left px-4 py-3 border-b hover:bg-accent transition-colors",
              selectedArticle?.id === article.id && "bg-accent",
              !article.is_read && "font-medium"
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <span className="text-sm leading-snug line-clamp-2">{article.title}</span>
              {!article.is_read && (
                <span className="mt-1 shrink-0 w-1.5 h-1.5 rounded-full bg-primary" />
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">{formatDate(article.published_at)}</p>
          </button>
        ))}
      </ScrollArea>
    </div>
  )
}
