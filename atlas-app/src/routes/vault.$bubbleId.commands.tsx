import { createFileRoute } from "@tanstack/react-router";
import { Sparkles, Plus, Baby, HeartPulse, UserX, Flame, PackageOpen, Dog, Lock, Bell } from "lucide-react";
import { useEffect, useState } from "react";

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.replace(/\/$/, "");
const SERVICE_KEY = import.meta.env.VITE_SUPABASE_SERVICE_KEY;

export const Route = createFileRoute("/vault/$bubbleId/commands")({
  component: CommandsPage,
  head: () => ({
    meta: [
      { title: "Guardian AI — Vault" },
      { name: "description", content: "Teach your AI camera what to watch for and protect your family." },
    ],
  }),
});

type Cmd = {
  icon: typeof Baby;
  title: string;
  rule: string;
  severity: "critical" | "high" | "info";
  active: boolean;
};

type AIAction = {
  id: string;
  created_at: string;
  event_type: string;
  event_subtype: string | null;
  metadata: Record<string, unknown>;
};

const initial: Cmd[] = [
  { icon: Baby, title: "Child unattended", rule: "Alert if a child isn't in view for 15 minutes", severity: "high", active: true },
  { icon: HeartPulse, title: "Person hurt", rule: "Alert if someone falls or doesn't move for 60s", severity: "critical", active: true },
  { icon: UserX, title: "Unknown person", rule: "Alert if an unrecognized face is detected", severity: "critical", active: true },
  { icon: Flame, title: "Smoke or fire", rule: "Alert on visible smoke or flame in any room", severity: "critical", active: false },
  { icon: PackageOpen, title: "Package at door", rule: "Notify when a package is left on the porch", severity: "info", active: true },
  { icon: Dog, title: "Pet on the couch", rule: "Notify when the dog gets on the living-room couch", severity: "info", active: false },
];

const severityStyle: Record<Cmd["severity"], string> = {
  critical: "bg-danger/15 text-danger",
  high: "bg-gold/15 text-gold",
  info: "bg-accent text-muted-foreground",
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function CommandsPage() {
  const { bubbleId } = Route.useParams();
  const [cmds, setCmds] = useState(initial);
  const [draft, setDraft] = useState("");
  const [aiActions, setAiActions] = useState<AIAction[]>([]);

  const toggle = (i: number) =>
    setCmds((c) => c.map((x, idx) => (idx === i ? { ...x, active: !x.active } : x)));

  const add = () => {
    if (!draft.trim()) return;
    setCmds((c) => [
      { icon: Sparkles, title: "Custom rule", rule: draft.trim(), severity: "high", active: true },
      ...c,
    ]);
    setDraft("");
  };

  useEffect(() => {
    if (!SUPABASE_URL || !SERVICE_KEY || !bubbleId) return;

    const fetchActions = () => {
      void fetch(
        `${SUPABASE_URL}/rest/v1/device_events?select=id,created_at,event_type,event_subtype,metadata` +
          `&bubble=eq.${bubbleId}` +
          `&event_type=in.(guardian_action,camera_lock)` +
          `&order=created_at.desc&limit=10`,
        {
          headers: {
            apikey: SERVICE_KEY,
            Authorization: `Bearer ${SERVICE_KEY}`,
          },
        },
      )
        .then((r) => (r.ok ? (r.json() as Promise<AIAction[]>) : Promise.resolve([])))
        .then(setAiActions)
        .catch(() => setAiActions([]));
    };

    fetchActions();
    const id = setInterval(fetchActions, 15_000);
    return () => clearInterval(id);
  }, [bubbleId]);

  const activeCount = cmds.filter((c) => c.active).length;

  return (
    <div className="px-5 pt-12">
      <header className="flex items-end justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Guardian AI</p>
          <h1 className="mt-1 font-display text-3xl">
            Watch list
          </h1>
        </div>
        <span className="rounded-full border border-border bg-card px-3 py-1 text-xs text-muted-foreground">
          {activeCount} active
        </span>
      </header>

      {/* Status card */}
      <section className="relative mt-5 overflow-hidden rounded-3xl border border-border bg-gradient-surface p-5 shadow-soft">
        <div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-gold/20 blur-3xl" />
        <div className="flex items-center gap-3">
          <span className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-gold text-gold-foreground shadow-gold">
            <Sparkles className="h-5 w-5" />
          </span>
          <div>
            <p className="font-display text-xl leading-tight">Your family is safe</p>
            <p className="text-xs text-muted-foreground">AI is monitoring 4 cameras in real time</p>
          </div>
        </div>
      </section>

      {/* New command */}
      <section className="mt-5">
        <label className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Teach a new rule</label>
        <div className="mt-2 flex items-center gap-2 rounded-2xl border border-border bg-card p-2 pl-4 focus-within:ring-1 focus-within:ring-gold">
          <Sparkles className="h-4 w-4 text-gold" />
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="Alert if the front gate stays open over 5 min..."
            className="flex-1 bg-transparent text-sm placeholder:text-muted-foreground/70 focus:outline-none"
          />
          <button
            onClick={add}
            className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-gold text-gold-foreground shadow-gold"
            aria-label="Add rule"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
      </section>

      {/* Command list */}
      <section className="mt-7">
        <h2 className="mb-3 text-xs uppercase tracking-[0.2em] text-muted-foreground">Commands</h2>
        <ul className="space-y-2">
          {cmds.map((c, i) => {
            const Icon = c.icon;
            return (
              <li key={i} className="flex items-center gap-3 rounded-2xl border border-border bg-card p-3">
                <span className={`grid h-11 w-11 place-items-center rounded-xl ${severityStyle[c.severity]}`}>
                  <Icon className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{c.title}</p>
                  <p className="truncate text-xs text-muted-foreground">{c.rule}</p>
                </div>
                <button
                  onClick={() => toggle(i)}
                  className={`relative h-6 w-11 rounded-full transition-colors ${c.active ? "bg-gradient-gold" : "bg-muted"}`}
                  aria-label="Toggle"
                >
                  <span
                    className={`absolute top-0.5 h-5 w-5 rounded-full bg-background shadow-soft transition-all ${
                      c.active ? "left-[22px]" : "left-0.5"
                    }`}
                  />
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      {/* Recent AI Actions */}
      <section className="mt-8 pb-8">
        <h2 className="mb-3 text-xs uppercase tracking-[0.2em] text-muted-foreground">Recent AI Actions</h2>
        {aiActions.length === 0 ? (
          <p className="text-xs text-muted-foreground">No actions taken yet. Guardian AI will respond here when incidents are detected.</p>
        ) : (
          <ul className="space-y-2">
            {aiActions.map((a) => {
              const isLock = a.event_type === "camera_lock";
              const message =
                (a.metadata?.message as string | undefined) ??
                (isLock ? "Camera locked by Guardian AI" : "Notification sent");
              const behavior = a.metadata?.person_behavior as string | undefined;
              return (
                <li
                  key={a.id}
                  className="rounded-2xl border border-border bg-card p-3"
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl ${
                        isLock ? "bg-danger/15 text-danger" : "bg-gold/15 text-gold"
                      }`}
                    >
                      {isLock ? <Lock className="h-4 w-4" /> : <Bell className="h-4 w-4" />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate text-sm font-medium">
                          {isLock ? "Camera locked" : "Notification sent"}
                        </p>
                        <span className="shrink-0 text-xs text-muted-foreground">
                          {formatTime(a.created_at)}
                        </span>
                      </div>
                      <p className="mt-0.5 truncate text-xs text-muted-foreground">{message}</p>
                      {behavior ? (
                        <p className="mt-1 line-clamp-2 text-xs text-foreground/70 italic">
                          "{behavior}"
                        </p>
                      ) : null}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
