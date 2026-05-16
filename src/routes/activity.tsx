import { createFileRoute } from "@tanstack/react-router";
import { Lock, Unlock, Video, UserCheck, AlertTriangle, KeyRound, Footprints } from "lucide-react";

export const Route = createFileRoute("/activity")({
  component: ActivityPage,
  head: () => ({
    meta: [
      { title: "Activity — Vault" },
      { name: "description", content: "Full timeline of doors, cameras and AI alerts." },
    ],
  }),
});

type Event = {
  time: string;
  title: string;
  who: string;
  type: "lock" | "unlock" | "motion" | "face" | "alert" | "key" | "ai";
};

const groups: { day: string; events: Event[] }[] = [
  {
    day: "Today",
    events: [
      { time: "9:42 AM", title: "Front door unlocked", who: "Hanna · fingerprint", type: "unlock" },
      { time: "9:41 AM", title: "Face recognized", who: "Hanna · 99% match", type: "face" },
      { time: "8:15 AM", title: "Motion detected", who: "Backyard camera", type: "motion" },
      { time: "7:03 AM", title: "Unknown person flagged", who: "AI · doorbell", type: "alert" },
      { time: "6:30 AM", title: "Front door locked", who: "Auto · schedule", type: "lock" },
    ],
  },
  {
    day: "Yesterday",
    events: [
      { time: "11:12 PM", title: "Guardian armed", who: "Night mode", type: "ai" },
      { time: "6:20 PM", title: "Package delivered", who: "Front porch", type: "motion" },
      { time: "4:48 PM", title: "eKey sent to Alex", who: "Expires in 24h", type: "key" },
      { time: "8:00 AM", title: "Front door unlocked", who: "PIN · 4-digit", type: "unlock" },
    ],
  },
];

const iconFor: Record<Event["type"], typeof Lock> = {
  lock: Lock, unlock: Unlock, motion: Footprints, face: UserCheck, alert: AlertTriangle, key: KeyRound, ai: Video,
};

const toneFor: Record<Event["type"], string> = {
  lock: "bg-accent text-foreground",
  unlock: "bg-success/15 text-success",
  motion: "bg-accent text-muted-foreground",
  face: "bg-gold/15 text-gold",
  alert: "bg-danger/15 text-danger",
  key: "bg-gold/15 text-gold",
  ai: "bg-accent text-foreground",
};

function ActivityPage() {
  return (
    <div className="px-5 pt-12">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Timeline</p>
        <h1 className="mt-1 font-display text-3xl">Activity</h1>
      </header>

      {/* filter chips */}
      <div className="mt-5 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {["All", "Locks", "Cameras", "AI alerts", "Keys"].map((f, i) => (
          <button
            key={f}
            className={`shrink-0 rounded-full border px-4 py-1.5 text-xs ${
              i === 0 ? "border-transparent bg-gradient-gold text-gold-foreground shadow-gold" : "border-border bg-card text-muted-foreground"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      <div className="mt-6 space-y-7">
        {groups.map((g) => (
          <section key={g.day}>
            <h2 className="mb-3 text-xs uppercase tracking-[0.2em] text-muted-foreground">{g.day}</h2>
            <ol className="relative space-y-3 border-l border-border pl-5">
              {g.events.map((e, i) => {
                const Icon = iconFor[e.type];
                return (
                  <li key={i} className="relative">
                    <span className="absolute -left-[27px] top-3 h-2 w-2 rounded-full bg-gold" />
                    <div className="flex items-center gap-3 rounded-2xl border border-border bg-card p-3">
                      <span className={`grid h-10 w-10 place-items-center rounded-xl ${toneFor[e.type]}`}>
                        <Icon className="h-4 w-4" />
                      </span>
                      <div className="flex-1">
                        <p className="text-sm">{e.title}</p>
                        <p className="text-xs text-muted-foreground">{e.who}</p>
                      </div>
                      <span className="text-xs text-muted-foreground">{e.time}</span>
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>
        ))}
      </div>
    </div>
  );
}
