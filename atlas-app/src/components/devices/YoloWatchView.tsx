import { useEffect, useState } from "react";
import { Eye, Circle, Play, Loader2 } from "lucide-react";

const STREAM_HOST = "http://localhost:8765";
const BACKEND = "http://localhost:8000";
const POLL_INTERVAL_MS = 2000;

export function YoloWatchView() {
  const [active, setActive] = useState(false);
  const [streamKey, setStreamKey] = useState(0);
  const [simState, setSimState] = useState<"idle" | "starting" | "running">("idle");

  // Poll the YOLO stream server every 2 seconds
  useEffect(() => {
    let prev = false;

    const poll = async () => {
      try {
        const res = await fetch(`${STREAM_HOST}/status`, { signal: AbortSignal.timeout(1500) });
        const data = (await res.json()) as { active: boolean };
        const next = Boolean(data.active);
        if (next !== prev) {
          prev = next;
          setActive(next);
          if (next) {
            setStreamKey((k) => k + 1);
            setSimState("running");
          } else if (simState === "running") {
            setSimState("idle");
          }
        }
      } catch {
        if (prev) {
          prev = false;
          setActive(false);
          setSimState("idle");
        }
      }
    };

    void poll();
    const id = setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleStartSimulation = async () => {
    setSimState("starting");
    try {
      await fetch(`${BACKEND}/api/simulate`, { method: "POST" });
    } catch {
      // backend may not be running — stream server will still come up if script is run manually
      setSimState("idle");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Stream window */}
      <div className="relative aspect-[4/5] overflow-hidden rounded-3xl border border-border bg-black">
        {active ? (
          <>
            <img
              key={streamKey}
              src={`${STREAM_HOST}/stream`}
              alt="YOLO live feed"
              className="absolute inset-0 h-full w-full object-cover"
            />
            <div className="scan-line pointer-events-none absolute inset-x-0 z-30 h-px bg-gold/60" />
            <div className="absolute inset-x-0 top-0 z-30 flex items-center p-4 text-xs text-white/80">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-black/40 px-2.5 py-1 backdrop-blur">
                <Circle className="h-2 w-2 fill-danger text-danger" /> LIVE · AI
              </span>
            </div>
          </>
        ) : (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-4 bg-gradient-to-br from-zinc-900 via-zinc-800 to-black p-6 text-center">
            <Eye className={`h-10 w-10 ${simState === "starting" ? "animate-pulse text-gold/60" : "text-muted-foreground/40"}`} />
            {simState === "starting" ? (
              <>
                <p className="text-sm text-muted-foreground">Analyzing footage…</p>
                <p className="text-xs text-muted-foreground/50">This takes 30–60 s the first time</p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Waiting for simulation</p>
            )}
          </div>
        )}
      </div>

      {/* Control */}
      {!active && simState !== "starting" && (
        <button
          type="button"
          onClick={() => void handleStartSimulation()}
          className="flex items-center justify-center gap-2 rounded-full bg-gradient-gold px-5 py-3 text-sm font-medium text-gold-foreground shadow-gold"
        >
          <Play className="h-4 w-4" />
          Start Simulation
        </button>
      )}
      {simState === "starting" && (
        <div className="flex items-center justify-center gap-2 rounded-full border border-border bg-card px-5 py-3 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Running pipeline…
        </div>
      )}

      <p className="text-center text-xs text-muted-foreground">
        Runs YOLO on the kidnapping footage and streams results live
      </p>
    </div>
  );
}
