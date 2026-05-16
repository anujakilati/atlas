import { Link, Outlet, useLocation, useNavigate } from "@tanstack/react-router";
import { Home, Video, ScrollText, Sparkles } from "lucide-react";
import { useEffect } from "react";
import { useAuth } from "@/contexts/auth-context";

const tabs = [
  { to: "/", icon: Home, label: "Home" },
  { to: "/camera", icon: Video, label: "Camera" },
  { to: "/activity", icon: ScrollText, label: "Activity" },
  { to: "/commands", icon: Sparkles, label: "AI" },
] as const;

export function AppShell() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { session, loading } = useAuth();
  const isAuthRoute = pathname === "/login" || pathname === "/signup";

  useEffect(() => {
    if (loading) return;
    if (!session && !isAuthRoute) {
      void navigate({ to: "/login" });
    }
    if (session && isAuthRoute) {
      void navigate({ to: "/" });
    }
  }, [session, loading, isAuthRoute, navigate]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  return (
    <div className="relative mx-auto flex min-h-screen w-full max-w-md flex-col bg-background">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[420px] bg-gradient-glow" />
      <main className={`relative flex-1 ${isAuthRoute ? "" : "pb-28"}`}>
        <Outlet />
      </main>
      {!isAuthRoute ? (
        <nav className="fixed inset-x-0 bottom-0 z-50 mx-auto w-full max-w-md px-4 pb-5">
          <div className="glass flex items-center justify-around rounded-full border border-border/60 px-2 py-2 shadow-soft">
            {tabs.map(({ to, icon: Icon, label }) => {
              const active = pathname === to;
              return (
                <Link
                  key={to}
                  to={to}
                  className={`flex flex-1 flex-col items-center gap-1 rounded-full px-3 py-2 transition-all ${
                    active ? "bg-gradient-gold text-gold-foreground shadow-gold" : "text-muted-foreground"
                  }`}
                >
                  <Icon className="h-[18px] w-[18px]" strokeWidth={active ? 2.4 : 1.8} />
                  <span className="text-[10px] font-medium tracking-wide">{label}</span>
                </Link>
              );
            })}
          </div>
        </nav>
      ) : null}
    </div>
  );
}
