import { createFileRoute, Link } from "@tanstack/react-router";
import { Lock, Unlock, Wifi, Battery, Bell, UserPlus, ChevronRight, ShieldCheck, Video, Plus, ChevronLeft } from "lucide-react";
import { AddMemberDialog } from "@/components/bubbles/AddMemberDialog";
import { useCallback, useEffect, useRef, useState } from "react";
import lockHero from "@/assets/lock-hero.jpg";
import { fetchBubble, type BubbleType } from "@/lib/bubbles";
import { bubbleTypeConfig } from "@/components/bubbles/bubble-styles";

export const Route = createFileRoute("/vault/$bubbleId")({
  component: VaultPage,
  head: () => ({
    meta: [{ title: "Vault" }],
  }),
});

function VaultPage() {
  const { bubbleId } = Route.useParams();
  const [locked, setLocked] = useState(true);
  const [bubbleName, setBubbleName] = useState("Your bubble");
  const [bubbleType, setBubbleType] = useState<BubbleType>("house");
  const [addMemberOpen, setAddMemberOpen] = useState(false);

  useEffect(() => {
    void fetchBubble(bubbleId)
      .then((b) => {
        setBubbleName(b.name);
        setBubbleType(b.type);
      })
      .catch(() => {
        setBubbleName("Your bubble");
      });
  }, [bubbleId]);

  const typeLabel = bubbleTypeConfig[bubbleType].label;

  return (
    <div className="px-5 pt-12">
      <header className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <Link
            to="/"
            className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground"
          >
            <ChevronLeft className="h-3 w-3" /> All bubbles
          </Link>
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{typeLabel}</p>
          <h1 className="mt-1 truncate font-display text-3xl leading-none">{bubbleName}</h1>
        </div>
        <button className="relative grid h-11 w-11 shrink-0 place-items-center rounded-full border border-border bg-card">
          <Bell className="h-4 w-4" />
          <span className="absolute right-2.5 top-2.5 h-1.5 w-1.5 rounded-full bg-gold" />
        </button>
      </header>

      <section className="relative mt-6 overflow-hidden rounded-3xl border border-border bg-card shadow-soft">
        <div className="relative h-64">
          <img
            src={lockHero}
            alt="Front door smart lock"
            className="absolute inset-0 h-full w-full object-cover opacity-90"
            width={1024}
            height={1280}
          />
          <div className="absolute inset-0 bg-gradient-to-t from-card via-card/30 to-transparent" />
          <div className="absolute left-5 top-5 flex items-center gap-2">
            <span className={`relative h-2 w-2 rounded-full ${locked ? "bg-success" : "bg-danger"}`}>
              <span className={`absolute inset-0 rounded-full ${locked ? "pulse-ring" : ""}`} />
            </span>
            <span className="text-xs uppercase tracking-wider text-foreground/80">
              {locked ? "Secured" : "Unlocked"}
            </span>
          </div>
          <div className="absolute right-5 top-5 flex items-center gap-3 text-xs text-foreground/70">
            <span className="inline-flex items-center gap-1">
              <Battery className="h-3.5 w-3.5" />
              98%
            </span>
            <span className="inline-flex items-center gap-1">
              <Wifi className="h-3.5 w-3.5" />
              5G
            </span>
          </div>
        </div>

        <div className="p-5 pt-2">
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Front Door</p>
          <h2 className="mt-1 font-display text-3xl">Main entrance</h2>
          <SlideToLock locked={locked} onToggle={() => setLocked((v) => !v)} />
        </div>
      </section>

      <section className="mt-5 grid grid-cols-2 gap-3">
        <QuickAction
          icon={UserPlus}
          title="Add member"
          subtitle="Share invite code"
          onClick={() => setAddMemberOpen(true)}
        />
        <QuickAction
          icon={Video}
          title="Live view"
          subtitle="2 cameras"
          bubbleId={bubbleId}
          to="camera"
        />
        <QuickAction
          icon={ShieldCheck}
          title="Guardian"
          subtitle="3 rules active"
          bubbleId={bubbleId}
          to="commands"
          accent
        />
        <QuickAction icon={Plus} title="New device" subtitle="Pair sensor" />
      </section>

      <AddMemberDialog
        bubbleId={bubbleId}
        bubbleName={bubbleName}
        open={addMemberOpen}
        onOpenChange={setAddMemberOpen}
      />

      <section className="mt-6">
        <div className="mb-3 flex items-end justify-between">
          <h3 className="font-display text-2xl">Today</h3>
          <Link
            to="/vault/$bubbleId/activity"
            params={{ bubbleId }}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground"
          >
            View all <ChevronRight className="h-3 w-3" />
          </Link>
        </div>
        <ul className="space-y-2">
          <ActivityRow time="9:42 AM" title="Front door unlocked" who="Hanna · fingerprint" tone="success" />
          <ActivityRow time="8:15 AM" title="Motion detected" who="Backyard camera" tone="muted" />
          <ActivityRow time="7:03 AM" title="Unknown face flagged" who="Doorbell · AI alert" tone="danger" />
        </ul>
      </section>
    </div>
  );
}

const THUMB_SIZE = 48;
const SLIDE_THRESHOLD = 0.85;

function SlideToLock({ locked, onToggle }: { locked: boolean; onToggle: () => void }) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [offset, setOffset] = useState(0);
  const offsetRef = useRef(0);
  const [maxOffset, setMaxOffset] = useState(0);
  const [dragging, setDragging] = useState(false);
  const draggingRef = useRef(false);
  const dragStart = useRef({ x: 0, offset: 0 });

  const measure = useCallback(() => {
    const track = trackRef.current;
    if (!track) return;
    const trackInset = 4;
    const next = Math.max(0, track.clientWidth - THUMB_SIZE - trackInset * 2);
    setMaxOffset(next);
  }, []);

  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  const setSlideOffset = useCallback((value: number) => {
    offsetRef.current = value;
    setOffset(value);
  }, []);

  useEffect(() => {
    setSlideOffset(locked ? 0 : maxOffset);
  }, [locked, maxOffset, setSlideOffset]);

  const progress = maxOffset > 0 ? offset / maxOffset : 0;

  const handlePointerDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    draggingRef.current = true;
    setDragging(true);
    dragStart.current = { x: e.clientX, offset };
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (!draggingRef.current) return;
    const delta = e.clientX - dragStart.current.x;
    const next = Math.max(0, Math.min(maxOffset, dragStart.current.offset + delta));
    setSlideOffset(next);
  };

  const finishDrag = () => {
    if (!draggingRef.current) return;
    draggingRef.current = false;
    setDragging(false);

    const currentProgress = maxOffset > 0 ? offsetRef.current / maxOffset : 0;
    const shouldUnlock = locked && currentProgress >= SLIDE_THRESHOLD;
    const shouldLock = !locked && currentProgress <= 1 - SLIDE_THRESHOLD;

    if (shouldUnlock || shouldLock) {
      onToggle();
    } else {
      setSlideOffset(locked ? 0 : maxOffset);
    }
  };

  return (
    <div
      ref={trackRef}
      className={`relative mt-5 h-14 w-full overflow-hidden rounded-2xl border border-border bg-background/40 touch-none select-none transition-shadow ${
        locked ? "" : "ring-gold"
      }`}
    >
      <div
        className="absolute inset-y-1 left-1 rounded-xl bg-gradient-gold/25"
        style={{
          width: offset + THUMB_SIZE,
          transition: dragging ? "none" : "width 0.35s cubic-bezier(0.34, 1.2, 0.64, 1)",
        }}
      />
      <span
        className="pointer-events-none absolute inset-0 flex items-center pl-5 font-medium"
        style={{
          opacity: 1 - progress * 0.65,
          transition: dragging ? "none" : "opacity 0.25s ease",
        }}
      >
        {locked ? "Slide to unlock" : "Slide to lock"}
      </span>
      <button
        type="button"
        data-thumb
        aria-label={locked ? "Slide to unlock" : "Slide to lock"}
        className="absolute top-1 left-1 z-10 grid h-12 w-12 cursor-grab place-items-center rounded-xl bg-gradient-gold text-gold-foreground shadow-gold active:cursor-grabbing active:scale-95"
        style={{
          transform: `translateX(${offset}px)`,
          transition: dragging ? "none" : "transform 0.35s cubic-bezier(0.34, 1.2, 0.64, 1)",
        }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={finishDrag}
        onPointerCancel={finishDrag}
        onLostPointerCapture={finishDrag}
      >
        {locked ? <Lock className="h-5 w-5" /> : <Unlock className="h-5 w-5" />}
      </button>
    </div>
  );
}

function QuickAction({
  icon: Icon,
  title,
  subtitle,
  bubbleId,
  to,
  accent,
  onClick,
}: {
  icon: typeof Lock;
  title: string;
  subtitle: string;
  bubbleId?: string;
  to?: "camera" | "commands";
  accent?: boolean;
  onClick?: () => void;
}) {
  const inner = (
    <div
      className={`relative h-full overflow-hidden rounded-2xl border border-border p-4 ${
        accent ? "bg-gradient-gold text-gold-foreground" : "bg-card"
      }`}
    >
      <Icon className="h-5 w-5" strokeWidth={1.8} />
      <p className="mt-6 text-sm font-medium">{title}</p>
      <p className={`text-xs ${accent ? "text-gold-foreground/70" : "text-muted-foreground"}`}>{subtitle}</p>
    </div>
  );

  if (to === "camera" && bubbleId) {
    return (
      <Link to="/vault/$bubbleId/camera" params={{ bubbleId }}>
        {inner}
      </Link>
    );
  }
  if (to === "commands" && bubbleId) {
    return (
      <Link to="/vault/$bubbleId/commands" params={{ bubbleId }}>
        {inner}
      </Link>
    );
  }
  return (
    <button type="button" className="text-left" onClick={onClick}>
      {inner}
    </button>
  );
}

function ActivityRow({
  time,
  title,
  who,
  tone,
}: {
  time: string;
  title: string;
  who: string;
  tone: "success" | "danger" | "muted";
}) {
  const dot = tone === "success" ? "bg-success" : tone === "danger" ? "bg-danger" : "bg-muted-foreground";
  return (
    <li className="flex items-center gap-3 rounded-2xl border border-border bg-card/60 p-3">
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      <div className="flex-1">
        <p className="text-sm">{title}</p>
        <p className="text-xs text-muted-foreground">{who}</p>
      </div>
      <span className="text-xs text-muted-foreground">{time}</span>
    </li>
  );
}
