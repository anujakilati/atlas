import { Link } from "@tanstack/react-router";
import type { Bubble } from "@/lib/bubbles";
import { bubbleTypeConfig } from "@/components/bubbles/bubble-styles";

export function BubbleTile({ bubble }: { bubble: Bubble }) {
  const config = bubbleTypeConfig[bubble.type];
  const Icon = config.icon;

  return (
    <Link
      to="/vault/$bubbleId"
      params={{ bubbleId: bubble.id }}
      className={`group relative flex min-h-[148px] flex-col justify-between overflow-hidden rounded-3xl border p-5 shadow-soft transition-transform active:scale-[0.98] ${config.card}`}
    >
      <div className={`pointer-events-none absolute inset-0 ${config.pattern}`} />
      <div className="relative flex items-start justify-between">
        <span className={`grid h-11 w-11 place-items-center rounded-2xl border border-border/50 bg-background/30 ${config.accent}`}>
          <Icon className="h-5 w-5" strokeWidth={1.8} />
        </span>
        <span className="rounded-full border border-border/60 bg-background/40 px-2 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
          {config.label}
        </span>
      </div>
      <div className="relative">
        <p className="font-display text-2xl leading-tight">{bubble.name}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {bubble.isOwner ? "You created this bubble" : "Member"} · tap to open
        </p>
      </div>
    </Link>
  );
}
