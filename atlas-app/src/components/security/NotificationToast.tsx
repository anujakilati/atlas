import { Bell, X, Sparkles } from "lucide-react";
import type { GuardianEvent } from "@/hooks/use-guardian-events";

type Props = {
  notifications: GuardianEvent[];
  onDismiss: (id: string) => void;
  onClear: () => void;
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function formatRelative(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 5) return "just now";
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return formatTime(iso);
}

function briefDescription(ev: GuardianEvent): string {
  const m = ev.metadata ?? {};
  const raw =
    (m.person_behavior as string | undefined) ??
    (m.message as string | undefined) ??
    "Suspicious activity detected.";
  // Trim to ~70 chars, end on a word boundary, append ellipsis
  const cleaned = raw.replace(/\s+/g, " ").trim();
  if (cleaned.length <= 70) return cleaned;
  const cut = cleaned.slice(0, 70);
  const lastSpace = cut.lastIndexOf(" ");
  return (lastSpace > 40 ? cut.slice(0, lastSpace) : cut) + "…";
}

function riskTint(level: string | null | undefined) {
  if (level === "critical") return "from-red-500/30 to-red-600/10 border-red-500/60";
  if (level === "high")     return "from-orange-500/30 to-red-500/10 border-orange-500/60";
  if (level === "medium")   return "from-amber-400/30 to-orange-500/10 border-amber-400/60";
  return "from-gold/30 to-amber-400/10 border-gold/50";
}

function riskBadge(level: string | null | undefined) {
  if (level === "critical") return "bg-red-500 text-white";
  if (level === "high")     return "bg-orange-500 text-white";
  if (level === "medium")   return "bg-amber-400 text-amber-950";
  return "bg-gold text-gold-foreground";
}

export function NotificationToast({ notifications, onDismiss, onClear }: Props) {
  if (notifications.length === 0) return null;

  return (
    <div className="fixed top-4 left-1/2 z-40 w-[min(94vw,440px)] -translate-x-1/2 animate-in slide-in-from-top duration-300">
      <div className="overflow-hidden rounded-2xl border border-gold/50 bg-card/95 shadow-2xl backdrop-blur-lg">
        {/* Header */}
        <div className="flex items-center justify-between bg-gradient-to-r from-gold/30 via-gold/15 to-transparent px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="relative grid h-7 w-7 place-items-center rounded-full bg-gold text-gold-foreground shadow-gold">
              <Bell className="h-3.5 w-3.5" />
              <span className="absolute -right-0.5 -top-0.5 h-2 w-2 animate-pulse rounded-full bg-red-500 ring-2 ring-card" />
            </span>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-gold">
                Guardian AI
              </p>
              <p className="text-xs font-medium text-foreground">
                {notifications.length} notification{notifications.length === 1 ? "" : "s"} sent
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClear}
            className="rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            Clear all
          </button>
        </div>

        {/* Scrollable notifications list */}
        <div className="max-h-[60vh] overflow-y-auto">
          <ul className="divide-y divide-border/50">
            {notifications.map((n) => {
              const tint = riskTint(n.risk_level);
              const badge = riskBadge(n.risk_level);
              return (
                <li
                  key={n.id}
                  className={`relative flex items-start gap-3 bg-gradient-to-r ${tint} border-l-4 px-3 py-2.5`}
                >
                  <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-background/70 text-foreground">
                    <Sparkles className="h-3.5 w-3.5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${badge}`}
                      >
                        {n.risk_level ?? "alert"}
                      </span>
                      <span className="text-[10px] font-medium uppercase tracking-wider text-foreground/70">
                        Notification sent
                      </span>
                      <span className="ml-auto text-[10px] text-muted-foreground">
                        {formatRelative(n.created_at)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-foreground/90 truncate">{briefDescription(n)}</p>
                    <p className="mt-0.5 text-[10px] text-muted-foreground">
                      {formatTime(n.created_at)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => onDismiss(n.id)}
                    aria-label="Dismiss"
                    className="grid h-6 w-6 shrink-0 place-items-center rounded-full text-muted-foreground hover:bg-background/60 hover:text-foreground"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}
