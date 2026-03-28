import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ExternalLink, MailOpen, Mail } from "lucide-react"
import { api } from "@/lib/api"

function formatDate(iso) {
  if (!iso) return ""
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  })
}

export default function ArticleView({ article, onArticleUpdate }) {
  if (!article) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground text-sm">
        Select an article to read
      </div>
    )
  }

  const toggleRead = async () => {
    const updated = article.is_read
      ? await api.markUnread(article.id)
      : await api.markRead(article.id)
    onArticleUpdate({ ...article, ...updated })
  }

  return (
    <div className="flex flex-col flex-1 min-w-0">
      {/* Article header */}
      <div className="px-8 py-5 border-b">
        <div className="flex items-start justify-between gap-4 mb-1">
          <h2 className="text-xl font-semibold leading-snug">{article.title}</h2>
          <div className="flex items-center gap-1 shrink-0 mt-0.5">
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={toggleRead} title={article.is_read ? "Mark unread" : "Mark read"}>
              {article.is_read ? <Mail className="h-4 w-4" /> : <MailOpen className="h-4 w-4" />}
            </Button>
            {article.link && (
              <Button variant="ghost" size="icon" className="h-8 w-8" asChild>
                <a href={article.link} target="_blank" rel="noopener noreferrer" title="Open original">
                  <ExternalLink className="h-4 w-4" />
                </a>
              </Button>
            )}
          </div>
        </div>
        <p className="text-sm text-muted-foreground">{formatDate(article.published_at)}</p>
      </div>

      {/* Article content */}
      <ScrollArea className="flex-1">
        <div
          className="px-8 py-6 prose prose-sm max-w-none"
          // RSS content is trusted HTML from feeds the user subscribed to
          dangerouslySetInnerHTML={{ __html: article.content }}
        />
      </ScrollArea>
    </div>
  )
}
