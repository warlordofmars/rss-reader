import { useState } from "react"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { LogOut } from "lucide-react"
import Logo from "./Logo"
import FeedSidebar from "./FeedSidebar"
import ArticleList from "./ArticleList"
import ArticleView from "./ArticleView"

export default function Layout({ user, onLogout }) {
  const [selectedFeedId, setSelectedFeedId] = useState(null)
  const [selectedArticle, setSelectedArticle] = useState(null)
  const [feeds, setFeeds] = useState([])

  const handleSelectFeed = (feedId) => {
    setSelectedFeedId(feedId)
    setSelectedArticle(null)
  }

  const handleArticleUpdate = (updated) => {
    setSelectedArticle(updated)
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* Top nav */}
      <header className="flex items-center justify-between px-4 h-12 border-b bg-primary text-primary-foreground shrink-0">
        <div className="flex items-center gap-2">
          <Logo size={24} />
          <span className="font-semibold text-sm">RSS Reader</span>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-8 gap-2 px-2 hover:bg-white/15 hover:text-primary-foreground">
              <Avatar className="h-6 w-6">
                <AvatarImage src={user.picture} />
                <AvatarFallback>{user.name?.[0]}</AvatarFallback>
              </Avatar>
              <span className="text-sm">{user.name}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onLogout} className="text-destructive">
              <LogOut className="h-4 w-4 mr-2" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </header>

      {/* Main 3-column layout */}
      <div className="flex flex-1 overflow-hidden">
        <FeedSidebar
          selectedFeedId={selectedFeedId}
          onSelectFeed={handleSelectFeed}
          feeds={feeds}
          setFeeds={setFeeds}
        />
        <ArticleList
          selectedFeedId={selectedFeedId}
          feeds={feeds}
          selectedArticle={selectedArticle}
          onSelectArticle={setSelectedArticle}
          onArticlesLoaded={() => {}}
        />
        <ArticleView
          article={selectedArticle}
          onArticleUpdate={handleArticleUpdate}
        />
      </div>
    </div>
  )
}
