import { createFileRoute } from "@tanstack/react-router";
import { AlertTriangle, Play, User, X, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { type DeviceEvent, type Character, fetchDeviceEvents, fetchCharacters } from "../lib/activities";
import { supabase } from "@/lib/supabase";
import { type Device, type DeviceRecording, fetchBubbleDevices, fetchBubbleRecordings } from "../lib/devices";
import { ActionsBadges, isActionEvent } from "@/components/security/ActionsBadges";

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

const EVENT_LABELS: Record<string, string> = {
  suspicious_person: "Suspicious Person",
  suspicious_behavior: "Suspicious Behavior",
  loitering: "Loitering",
  theft: "Theft",
  kidnapping: "Kidnapping",
  trespassing: "Trespassing",
  false_alarm: "False Alarm",
  unknown_person: "Unknown Person",
  guardian_action: "Guardian AI Action",
  camera_lock: "Camera Locked",
};

function formatEventTitle(ev: DeviceEvent): string {
  // Prefer a label derived from event_type or event_subtype
  const raw = ev.event_type ?? "";
  return EVENT_LABELS[raw] ?? (raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) || "Suspicious Event");
}

function getEventDescription(ev: DeviceEvent): string | null {
  const m = ev.metadata ?? {};
  // person_behavior is set by Nemotron (most descriptive)
  if (typeof m.person_behavior === "string" && m.person_behavior.trim()) return m.person_behavior.trim();
  // character_profile.summary is set by show_latest_event.py
  const cp = m.character_profile as Record<string, unknown> | undefined;
  if (cp && typeof cp.summary === "string" && cp.summary.trim()) return cp.summary.trim();
  // fallback to general summary
  if (typeof m.summary === "string" && m.summary.trim()) return m.summary.trim();
  // guardian action message
  if (typeof m.message === "string" && m.message.trim()) return m.message.trim();
  return null;
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

const RECORDING_MATCH_MS = 5 * 60 * 1000; // 5-minute window for timestamp matching

function nearestRecording(event: DeviceEvent, recordings: DeviceRecording[]): DeviceRecording | null {
  const eventMs = new Date(event.created_at).getTime();
  let best: DeviceRecording | null = null;
  let bestDelta = Infinity;
  for (const rec of recordings) {
    const delta = Math.abs(eventMs - new Date(rec.createdAt).getTime());
    if (delta < RECORDING_MATCH_MS && delta < bestDelta) {
      best = rec;
      bestDelta = delta;
    }
  }
  return best;
}

function ActivityPage() {
  const { bubbleId } = Route.useParams();
  const [tab, setTab] = useState<"moments" | "characters">("moments");
  const [events, setEvents] = useState<DeviceEvent[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [recordings, setRecordings] = useState<DeviceRecording[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [loadingMoments, setLoadingMoments] = useState(true);
  const [loadingCharacters, setLoadingCharacters] = useState(true);
  const [playingEventId, setPlayingEventId] = useState<string | null>(null);
  const [focusedCharacterId, setFocusedCharacterId] = useState<number | null>(null);
  const characterRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  const loadMoments = useCallback(() => {
    void fetchDeviceEvents(bubbleId)
      .then(setEvents)
      .catch((e) => { console.error("[moments]", e); setEvents([]); })
      .finally(() => setLoadingMoments(false));
  }, [bubbleId]);

  const loadCharacters = useCallback(() => {
    void fetchCharacters()
      .then(setCharacters)
      .catch((e) => { console.error("[characters]", e); setCharacters([]); })
      .finally(() => setLoadingCharacters(false));
  }, []);

  const loadRecordings = useCallback(() => {
    void fetchBubbleRecordings(bubbleId)
      .then(setRecordings)
      .catch((e) => { console.error("[recordings]", e); });
  }, [bubbleId]);

  const loadDevices = useCallback(() => {
    void fetchBubbleDevices(bubbleId)
      .then(setDevices)
      .catch((e) => { console.error("[devices]", e); });
  }, [bubbleId]);

  useEffect(() => {
    loadMoments();
    loadCharacters();
    loadRecordings();
    loadDevices();
    const id = setInterval(() => {
      loadMoments();
      loadCharacters();
      loadRecordings();
      loadDevices();
    }, 30_000);
    return () => clearInterval(id);
  }, [loadMoments, loadCharacters, loadRecordings, loadDevices]);

  // Realtime: refresh moments + characters the instant a new event is inserted
  useEffect(() => {
    const channel = supabase
      .channel(`activity-events-${bubbleId}`)
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "device_events" },
        () => { loadMoments(); loadCharacters(); },
      )
      .subscribe();
    return () => { void supabase.removeChannel(channel); };
  }, [bubbleId, loadMoments, loadCharacters]);

  const incidentEvents = events.filter((ev) => !isActionEvent(ev));
  const groups = groupByDay(incidentEvents);

  const findCharacterForEvent = (ev: DeviceEvent): Character | null => {
    const cropUrl = ev.metadata?.profile_crop_url as string | undefined;
    if (!cropUrl) return null;
    return characters.find((c) => c.profile_crop_url === cropUrl) ?? null;
  };

  const handleViewPerson = (character: Character) => {
    setFocusedCharacterId(character.id);
    setTab("characters");
    // scroll after tab renders
    requestAnimationFrame(() => {
      const el = characterRefs.current.get(character.id);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  };

  return (
    <div className="px-5 pt-12 pb-8">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Timeline</p>
        <h1 className="mt-1 font-display text-3xl">Activity</h1>
      </header>

      {/* tab bar */}
      <div className="mt-5 flex gap-2">
        <button
          onClick={() => { setTab("moments"); setFocusedCharacterId(null); }}
          className={`flex-1 rounded-full border px-4 py-2 text-xs font-medium transition-all ${
            tab === "moments"
              ? "border-transparent bg-gradient-gold text-gold-foreground shadow-gold"
              : "border-border bg-card text-muted-foreground"
          }`}
        >
          Suspicious Moments
        </button>
        <button
          onClick={() => { setTab("characters"); setFocusedCharacterId(null); }}
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
          ) : incidentEvents.length === 0 ? (
            <p className="mt-16 text-center text-sm text-muted-foreground">No suspicious activity detected yet.</p>
          ) : (
            groups.map((g) => (
              <section key={g.day}>
                <h2 className="mb-3 text-xs uppercase tracking-[0.2em] text-muted-foreground">{g.day}</h2>
                <ol className="relative space-y-3 border-l border-border pl-5">
                  {g.items.map((ev) => {
                    const title = formatEventTitle(ev);
                    const description = getEventDescription(ev);
                    const deviceName = devices.find((d) => d.id === ev.device)?.name;
                    const badge = [deviceName, ev.risk_level ? `${ev.risk_level} risk` : null]
                      .filter(Boolean)
                      .join(" · ");
                    const replayUrl = (ev.metadata?.replay_url as string | undefined)
                      ?? nearestRecording(ev, recordings)?.publicUrl;
                    const isPlaying = playingEventId === ev.id;
                    const linkedCharacter = findCharacterForEvent(ev);
                    return (
                      <li key={ev.id} className="relative">
                        <span className="absolute -left-[27px] top-3 h-2 w-2 rounded-full bg-gold" />
                        <div className="rounded-2xl border border-border bg-card p-3">
                          <div className="flex items-start gap-3">
                            <span className={`mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-xl ${riskColor(ev.risk_level)}`}>
                              <AlertTriangle className="h-4 w-4" />
                            </span>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium">{title}</p>
                              {description && (
                                <p className="mt-0.5 text-xs text-foreground/80 line-clamp-2">{description}</p>
                              )}
                              {badge && (
                                <p className="mt-1 text-xs text-muted-foreground truncate">{badge}</p>
                              )}
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              {replayUrl && (
                                <button
                                  onClick={() => setPlayingEventId(isPlaying ? null : ev.id)}
                                  className="grid h-7 w-7 place-items-center rounded-lg bg-gold/15 text-gold hover:bg-gold/25 transition-colors"
                                  aria-label={isPlaying ? "Close replay" : "Play replay"}
                                >
                                  {isPlaying ? <X className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                                </button>
                              )}
                              <span className="text-xs text-muted-foreground">{formatTime(ev.created_at)}</span>
                            </div>
                          </div>
                          {isPlaying && replayUrl && (
                            <div className="mt-3">
                              <video
                                src={replayUrl}
                                controls
                                autoPlay
                                className="w-full rounded-xl bg-black/20 max-h-64 object-contain"
                              />
                            </div>
                          )}
                          {linkedCharacter && (
                            <button
                              onClick={() => handleViewPerson(linkedCharacter)}
                              className="mt-2 flex w-full items-center gap-1.5 rounded-xl border border-border bg-accent/30 px-3 py-2 text-xs text-foreground/80 transition hover:bg-accent/60"
                            >
                              <User className="h-3.5 w-3.5 text-danger shrink-0" />
                              <span className="flex-1 text-left">View suspect profile</span>
                              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                            </button>
                          )}
                          <ActionsBadges
                            incidentId={(ev.metadata?.incident_id as string | undefined) ?? ev.id}
                            event={ev}
                            allEvents={events}
                          />
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
            characters.map((c) => {
              const isFocused = focusedCharacterId === c.id;
              return (
                <div
                  key={c.id}
                  ref={(el) => {
                    if (el) characterRefs.current.set(c.id, el);
                    else characterRefs.current.delete(c.id);
                  }}
                  className={`rounded-2xl border bg-card overflow-hidden transition-all ${
                    isFocused ? "border-danger shadow-[0_0_0_2px_rgba(239,68,68,0.4)]" : "border-border"
                  }`}
                >
                  {c.profile_crop_url && (
                    <img
                      src={c.profile_crop_url}
                      alt="Suspect"
                      className="w-full object-contain max-h-64 bg-black/20"
                    />
                  )}
                  <div className="p-4">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`grid h-6 w-6 place-items-center rounded-lg ${isFocused ? "bg-danger/25 text-danger" : "bg-danger/15 text-danger"}`}>
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
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
