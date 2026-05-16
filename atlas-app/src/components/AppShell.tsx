import { Link, Outlet, useLocation, useNavigate } from "@tanstack/react-router";
import { Home, Video, ScrollText, Sparkles } from "lucide-react";
import { useEffect, useMemo } from "react";
import { useAuth } from "@/contexts/auth-context";
import { getDeviceSession } from "@/lib/device-session";

export function AppShell() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { session, loading } = useAuth();
  const isAuthRoute = pathname === "/login" || pathname === "/signup";
  const isDeviceRoute = pathname.startsWith("/device");
  const isDashboard = pathname === "/";

  const bubbleId = useMemo(() => {
    const match = pathname.match(/^\/vault\/([^/]+)/);
    return match?.[1];
  }, [pathname]);

  const tabs = bubbleId
    ? [
        { to: "/vault/$bubbleId/" as const, label: "Home", icon: Home },
        { to: "/vault/$bubbleId/camera" as const, label: "Camera", icon: Video },
        { to: "/vault/$bubbleId/activity" as const, label: "Activity", icon: ScrollText },
        { to: "/vault/$bubbleId/commands" as const, label: "AI", icon: Sparkles },
      ]
    : [];

  useEffect(() => {
    if (loading) return;

    const deviceSession = getDeviceSession();

    // Registered camera devices: stream only, no vault UI
    if (deviceSession && !isDeviceRoute) {
      void navigate({ to: "/device/live", replace: true });
      return;
    }

    if (!session && !isAuthRoute && !isDeviceRoute) {
      void navigate({ to: "/login", replace: true });
    } else if (session && isAuthRoute) {
      void navigate({ to: "/", replace: true });
    }
  }, [session, loading, isAuthRoute, isDeviceRoute, navigate]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  const showNav = Boolean(bubbleId) && !isDeviceRoute;

  return (
    <div className="relative mx-auto flex min-h-screen w-full max-w-md flex-col bg-background">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[420px] bg-gradient-glow" />
      <main
        className={`relative flex-1 ${showNav || isDashboard || isAuthRoute || isDeviceRoute ? (showNav ? "pb-28" : "pb-8") : "pb-28"}`}
      >
        <Outlet />
      </main>
      {showNav && bubbleId ? (
        <nav className="fixed inset-x-0 bottom-0 z-50 mx-auto w-full max-w-md px-4 pb-5">
          <div className="glass flex items-center justify-around rounded-full border border-border/60 px-2 py-2 shadow-soft">
            {tabs.map(({ to, icon: Icon, label }) => {
              const homePath = `/vault/${bubbleId}`;
              const tabPath =
                to === "/vault/$bubbleId/"
                  ? homePath
                  : `/vault/${bubbleId}/${to.replace("/vault/$bubbleId/", "")}`;
              const active =
                to === "/vault/$bubbleId/"
                  ? pathname === homePath || pathname === `${homePath}/`
                  : pathname === tabPath || pathname.startsWith(`${tabPath}/`);
              return (
                <Link
                  key={to}
                  to={to}
                  params={{ bubbleId }}
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
