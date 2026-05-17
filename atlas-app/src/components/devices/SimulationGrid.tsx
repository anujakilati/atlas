import { useEffect, useState } from "react";
import { Circle, Eye } from "lucide-react";

const STREAM_HOST = "http://localhost:8765";
const POLL_INTERVAL_MS = 2000;
const CAM_COUNT = 4;

type StatusResponse = {
  active: boolean;
  cams?: { id: number; label: string }[];
};

export function SimulationGrid() {
  const [active, setActive] = useState(false);
  const [cams, setCams] = useState<{ id: number; label: string }[]>(
    Array.from({ length: CAM_COUNT }, (_, i) => ({ id: i + 1, label: `Sim Cam ${i + 1}` })),
  );
  const [streamKey, setStreamKey] = useState(0);

  useEffect(() => {
    let prev = false;
    const poll = async () => {
      try {
        const res = await fetch(`${STREAM_HOST}/status`, { signal: AbortSignal.timeout(1500) });
        const data = (await res.json()) as StatusResponse;
        const next = Boolean(data.active);
        if (data.cams && data.cams.length > 0) setCams(data.cams);
        if (next !== prev) {
          prev = next;
          setActive(next);
          if (next) setStreamKey((k) => k + 1);
        }
      } catch {
        if (prev) {
          prev = false;
          setActive(false);
        }
      }
    };
    void poll();
    const id = setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  if (!active) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-3xl border border-border bg-card p-12 text-center">
        <Eye className="h-10 w-10 text-muted-foreground/40" />
        <p className="text-sm text-muted-foreground">Waiting for simulation</p>
        <p className="font-mono text-[11px] text-muted-foreground/60">
          python scripts/yolo_multi_watch.py
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-3">
      {cams.map((cam) => (
        <div key={cam.id} className="flex flex-col gap-1">
          <div className="relative aspect-[4/3] overflow-hidden rounded-2xl border border-border bg-black">
            <img
              key={`${cam.id}-${streamKey}`}
              src={`${STREAM_HOST}/stream/${cam.id}`}
              alt={cam.label}
              className="absolute inset-0 h-full w-full object-cover"
            />
            <div className="scan-line pointer-events-none absolute inset-x-0 z-30 h-px bg-gold/60" />
            <div className="absolute inset-x-0 top-0 z-30 flex items-center p-2 text-[10px] text-white/80">
              <span className="inline-flex items-center gap-1 rounded-full bg-black/40 px-2 py-0.5 backdrop-blur">
                <Circle className="h-1.5 w-1.5 fill-danger text-danger" /> LIVE · AI
              </span>
            </div>
          </div>
          <p className="truncate px-1 text-xs text-muted-foreground">{cam.label}</p>
        </div>
      ))}
    </div>
  );
}
