import { createFileRoute } from "@tanstack/react-router";
import { Mic, MicOff, Volume2, Maximize2, Play, Circle } from "lucide-react";
import { useState } from "react";

export const Route = createFileRoute("/camera")({
  component: CameraPage,
  head: () => ({
    meta: [
      { title: "Live View — Vault" },
      { name: "description", content: "Live camera feeds and past recordings from your home." },
    ],
  }),
});

const cameras = [
  { id: "front", name: "Front Door", live: true },
  { id: "back", name: "Backyard", live: true },
  { id: "living", name: "Living Room", live: false },
  { id: "garage", name: "Garage", live: true },
];

const recordings = [
  { time: "Today · 9:42 AM", label: "Hanna entered", dur: "0:14" },
  { time: "Today · 7:03 AM", label: "Unknown person at door", dur: "0:38", danger: true },
  { time: "Yesterday · 6:20 PM", label: "Package delivered", dur: "0:09" },
  { time: "Yesterday · 2:11 PM", label: "Motion in backyard", dur: "0:22" },
];

function CameraPage() {
  const [active, setActive] = useState(cameras[0]);
  const [muted, setMuted] = useState(true);

  return (
    <div className="px-5 pt-12">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Live view</p>
        <h1 className="mt-1 font-display text-3xl">{active.name}</h1>
      </header>

      {/* Live viewer */}
      <div className="relative mt-5 aspect-[4/5] overflow-hidden rounded-3xl border border-border bg-black">
        <div className="absolute inset-0 bg-gradient-to-br from-zinc-900 via-zinc-800 to-black" />
        {/* faux noise / scan */}
        <div className="scan-line absolute inset-x-0 h-px bg-gold/60" />
        <div className="absolute inset-0 opacity-30 mix-blend-overlay [background-image:radial-gradient(circle_at_30%_40%,rgba(255,255,255,0.15),transparent_50%),radial-gradient(circle_at_70%_70%,rgba(255,255,255,0.1),transparent_50%)]" />

        {/* HUD top */}
        <div className="absolute inset-x-0 top-0 flex items-center justify-between p-4 text-xs text-white/80">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-black/40 px-2.5 py-1 backdrop-blur">
            <Circle className="h-2 w-2 fill-danger text-danger" /> LIVE
          </span>
          <span className="rounded-full bg-black/40 px-2.5 py-1 backdrop-blur">1080p · 5G</span>
        </div>

        {/* AI overlay box */}
        <div className="absolute left-[22%] top-[35%] h-32 w-24 rounded-md border border-gold/80 shadow-gold">
          <span className="absolute -top-5 left-0 rounded-sm bg-gold px-1.5 text-[10px] font-medium text-gold-foreground">
            Person · 98%
          </span>
        </div>

        {/* HUD bottom */}
        <div className="absolute inset-x-0 bottom-0 flex items-center justify-between p-4">
          <button
            onClick={() => setMuted((v) => !v)}
            className="glass grid h-11 w-11 place-items-center rounded-full border border-white/10 text-white"
          >
            {muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
          </button>
          <button className="grid h-14 w-14 place-items-center rounded-full bg-gradient-gold text-gold-foreground shadow-gold">
            <Volume2 className="h-5 w-5" />
          </button>
          <button className="glass grid h-11 w-11 place-items-center rounded-full border border-white/10 text-white">
            <Maximize2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Camera switcher */}
      <div className="mt-5 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {cameras.map((c) => {
          const isActive = c.id === active.id;
          return (
            <button
              key={c.id}
              onClick={() => setActive(c)}
              className={`shrink-0 rounded-full border px-4 py-2 text-xs transition ${
                isActive
                  ? "border-transparent bg-gradient-gold text-gold-foreground shadow-gold"
                  : "border-border bg-card text-muted-foreground"
              }`}
            >
              <span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${c.live ? "bg-success" : "bg-muted-foreground"}`} />
              {c.name}
            </button>
          );
        })}
      </div>

      {/* Recordings */}
      <section className="mt-7">
        <h2 className="font-display text-2xl">Recordings</h2>
        <ul className="mt-3 space-y-2">
          {recordings.map((r, i) => (
            <li key={i} className="flex items-center gap-3 rounded-2xl border border-border bg-card p-3">
              <span className={`grid h-12 w-12 place-items-center rounded-xl ${r.danger ? "bg-danger/15 text-danger" : "bg-accent text-foreground"}`}>
                <Play className="h-4 w-4" />
              </span>
              <div className="flex-1">
                <p className="text-sm">{r.label}</p>
                <p className="text-xs text-muted-foreground">{r.time}</p>
              </div>
              <span className="text-xs text-muted-foreground">{r.dur}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
