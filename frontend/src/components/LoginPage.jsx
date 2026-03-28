import { Button } from "@/components/ui/button"
import Logo from "./Logo"

export default function LoginPage() {
  return (
    <div className="flex items-center justify-center h-screen bg-background">
      <div className="flex flex-col items-center gap-6 p-10 rounded-2xl border bg-card shadow-sm w-full max-w-sm">
        <div className="flex flex-col items-center gap-2">
          <Logo size={52} />
          <h1 className="text-2xl font-semibold tracking-tight">RSS Reader</h1>
          <p className="text-sm text-muted-foreground text-center">
            Your personal feed, all in one place.
          </p>
        </div>

        <Button
          className="w-full"
          onClick={() => (window.location.href = "http://localhost:8000/auth/login")}
        >
          Sign in with Google
        </Button>
      </div>
    </div>
  )
}
