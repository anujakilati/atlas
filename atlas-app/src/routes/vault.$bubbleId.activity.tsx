import { createFileRoute } from "@tanstack/react-router";
import { AlertTriangle, User } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { type DeviceEvent, type Character, fetchDeviceEvents, fetchCharacters } from "../lib/activities";

export const Route = createFileRoute("/vault/$bubbleId/activity")({
  component: ActivityPage,
  head: () => ({
    meta: [
      { title: "Activity — Vault" },
      { name: "description", content: "Full timeline of suspicious moments and flagged characters." },
    ],
  }),
});

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function formatDay(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);

  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function groupByDay(items: DeviceEvent[]): { day: string; items: DeviceEvent[] }[] {
  const map = new Map<string, DeviceEvent[]>();
  for (const item of items) {
    const day = formatDay(item.created_at);
    if (!map.has(day)) map.set(day, []);
    map.get(day)!.push(item);
  }
  return Array.from(map.entries()).map(([day, items]) => ({ day, items }));
}

function riskColor(level: string | null) {
  if (level === "high" || level === "critical") return "bg-danger/15 text-danger";
  if (level === "medium") return "bg-orange-500/15 text-orange-500";
  return "bg-muted/30 text-muted-foreground";
}

function SkeletonCard() {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-border bg-card p-3 animate-pulse">
      <span className="h-10 w-10 rounded-xl bg-accent shrink-0" />
      <div className="flex-1 space-y-2">
        <div className="h-3 w-2/3 rounded bg-accent" />
        <div className="h-2.5 w-1/2 rounded bg-accent" />
      </div>
      <div className="h-2.5 w-12 rounded bg-accent" />
    </div>
  );
}

function ActivityPage() {
  const [tab, setTab] = useState<"moments" | "characters">("moments");
  const [events, setEvents] = useState<DeviceEvent[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [loadingMoments, setLoadingMoments] = useState(true);
  const [loadingCharacters, setLoadingCharacters] = useState(true);

  const loadMoments = useCallback(() => {
    void fetchDeviceEvents()
      .then(setEvents)
      .catch((e) => { console.error("[moments]", e); setEvents([]); })
      .finally(() => setLoadingMoments(false));
  }, []);

  const loadCharacters = useCallback(() => {
    void fetchCharacters()
      .then(setCharacters)
      .catch((e) => { console.error("[characters]", e); setCharacters([]); })
      .finally(() => setLoadingCharacters(false));
  }, []);

  useEffect(() => {
    loadMoments();
    loadCharacters();
    const id = setInterval(() => {
      loadMoments();
      loadCharacters();
    }, 30_000);
    return () => clearInterval(id);
  }, [loadMoments, loadCharacters]);

  const groups = groupByDay(events);

  return (
    <div className="px-5 pt-12 pb-8">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Timeline</p>
        <h1 className="mt-1 font-display text-3xl">Activity</h1>
      </header>

      {/* tab bar */}
      <div className="mt-5 flex gap-2">
        <button
          onClick={() => setTab("moments")}
          className={`flex-1 rounded-full border px-4 py-2 text-xs font-medium transition-all ${
            tab === "moments"
              ? "border-transparent bg-gradient-gold text-gold-foreground shadow-gold"
              : "border-border bg-card text-muted-foreground"
          }`}
        >
          Suspicious Moments
        </button>
        <button
          onClick={() => setTab("characters")}
          className={`flex-1 rounded-full border px-4 py-2 text-xs font-medium transition-all ${
            tab === "characters"
              ? "border-transparent bg-gradient-gold text-gold-foreground shadow-gold"
              : "border-border bg-card text-muted-foreground"
          }`}
        >
          Suspicious Characters
        </button>
      </div>

      {/* moments tab */}
      {tab === "moments" && (
        <div className="mt-6 space-y-7">
          {loadingMoments ? (
            <div className="space-y-3">
              <SkeletonCard />
              <SkeletonCard />
              <SkeletonCard />
            </div>
          ) : events.length === 0 ? (
            <p className="mt-16 text-center text-sm text-muted-foreground">No suspicious activity detected yet.</p>
          ) : (
            groups.map((g) => (
              <section key={g.day}>
                <h2 className="mb-3 text-xs uppercase tracking-[0.2em] text-muted-foreground">{g.day}</h2>
                <ol className="relative space-y-3 border-l border-border pl-5">
                  {g.items.map((ev) => {
                    const deviceName = ev.event_type ?? "Suspicious Event";
                    const subtitle = [ev.event_subtype, ev.risk_level ? `${ev.risk_level} risk` : null]
                      .filter(Boolean)
                      .join(" · ");
                    return (
                      <li key={ev.id} className="relative">
                        <span className="absolute -left-[27px] top-3 h-2 w-2 rounded-full bg-gold" />
                        <div className="rounded-2xl border border-border bg-card p-3">
                          <div className="flex items-center gap-3">
                            <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${riskColor(ev.risk_level)}`}>
                              <AlertTriangle className="h-4 w-4" />
                            </span>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium truncate">{deviceName}</p>
                              {subtitle && (
                                <p className="text-xs text-muted-foreground truncate">{subtitle}</p>
                              )}
                            </div>
                            <span className="shrink-0 text-xs text-muted-foreground">{formatTime(ev.created_at)}</span>
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </section>
            ))
          )}
        </div>
      )}

      {/* characters tab */}
      {tab === "characters" && (
        <div className="mt-6 space-y-3">
          {loadingCharacters ? (
            <>
              <SkeletonCard />
              <SkeletonCard />
            </>
          ) : characters.length === 0 ? (
            <p className="mt-16 text-center text-sm text-muted-foreground">No suspicious characters identified yet.</p>
          ) : (
            characters.map((c) => (
              <div key={c.id} className="rounded-2xl border border-border bg-card overflow-hidden">
                {c.profile_crop_url && (
                  <img
                    src={c.profile_crop_url}
                    alt="Suspect"
                    className="w-full object-contain max-h-64 bg-black/20"
                  />
                )}
                <div className="p-4">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="grid h-6 w-6 place-items-center rounded-lg bg-danger/15 text-danger">
                      <User className="h-3.5 w-3.5" />
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatTime(c.created_at)} · {formatDay(c.created_at)}
                    </span>
                  </div>
                  {c.sus_character_description && (
                    <p className="mt-2 text-sm text-foreground leading-relaxed">
                      {c.sus_character_description}
                    </p>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
