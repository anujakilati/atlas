import { createFileRoute } from "@tanstack/react-router";
import { Mic, MicOff, Volume2, Maximize2, Play, Circle, Video } from "lucide-react";
import { useEffect, useState } from "react";
import {
  fetchBubbleDevices,
  fetchDeviceRecordings,
  type Device,
  type DeviceRecording,
} from "@/lib/devices";
import { useDeviceStream } from "@/hooks/use-device-stream";
import { useStorageLiveFeed } from "@/hooks/use-storage-live-feed";

export const Route = createFileRoute("/vault/$bubbleId/camera")({
  component: CameraPage,
  head: () => ({
    meta: [
      { title: "Live View — Vault" },
      { name: "description", content: "Live camera feeds and past recordings from your home." },
    ],
  }),
});

function CameraPage() {
  const { bubbleId } = Route.useParams();
  const [devices, setDevices] = useState<Device[]>([]);
  const [recordings, setRecordings] = useState<DeviceRecording[]>([]);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState<Device | null>(null);
  const [muted, setMuted] = useState(true);

  const { videoRef, connected, waiting, error } = useDeviceStream(active?.id ?? null, "viewer");
  const storageLiveSrc = useStorageLiveFeed(active?.id ?? null, !connected && active?.status === "online");

  useEffect(() => {
    void fetchBubbleDevices(bubbleId)
      .then((list) => {
        setDevices(list);
        setActive(list[0] ?? null);
      })
      .catch(() => setDevices([]))
      .finally(() => setLoading(false));
  }, [bubbleId]);

  useEffect(() => {
    if (!active?.id) {
      setRecordings([]);
      return;
    }
    void fetchDeviceRecordings(active.id)
      .then(setRecordings)
      .catch(() => setRecordings([]));
    const id = setInterval(() => {
      void fetchDeviceRecordings(active.id).then(setRecordings).catch(() => undefined);
    }, 20000);
    return () => clearInterval(id);
  }, [active?.id]);

  const showWebRtc = connected;
  const showStorageLive = !connected && Boolean(storageLiveSrc);
  const isLive = showWebRtc || showStorageLive || active?.status === "online";

  return (
    <div className="px-5 pt-12">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Live view</p>
        <h1 className="mt-1 font-display text-3xl">{active?.name ?? "Cameras"}</h1>
        {active ? <p className="mt-0.5 text-sm text-muted-foreground">{active.placement}</p> : null}
      </header>

      <div className="relative mt-5 aspect-[4/5] overflow-hidden rounded-3xl border border-border bg-black">
        {active && showWebRtc ? (
          <video
            ref={videoRef}
            playsInline
            autoPlay
            muted={muted}
            className="absolute inset-0 h-full w-full object-cover"
          />
        ) : null}

        {active && showStorageLive ? (
          <video
            key={storageLiveSrc}
            src={storageLiveSrc ?? undefined}
            playsInline
            autoPlay
            muted={muted}
            className="absolute inset-0 h-full w-full object-cover"
          />
        ) : null}

        {(!active && !loading) || (active && waiting && !showWebRtc && !showStorageLive) ? (
          <div className="absolute inset-0 bg-gradient-to-br from-zinc-900 via-zinc-800 to-black">
            {!active && !loading ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center">
                <Video className="h-10 w-10 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  No cameras yet. Add a device and send the camera link.
                </p>
              </div>
            ) : (
              <WaitingOverlay deviceName={active!.name} />
            )}
          </div>
        ) : null}

        {isLive ? (
          <div className="scan-line pointer-events-none absolute inset-x-0 h-px bg-gold/60" />
        ) : null}

        <div className="absolute inset-x-0 top-0 flex items-center justify-between p-4 text-xs text-white/80">
          {isLive ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-black/40 px-2.5 py-1 backdrop-blur">
              <Circle className="h-2 w-2 fill-danger text-danger" /> LIVE
            </span>
          ) : (
            <span className="rounded-full bg-black/40 px-2.5 py-1 backdrop-blur text-muted-foreground">
              {active ? "Waiting for camera" : "Offline"}
            </span>
          )}
          {active ? (
            <span className="rounded-full bg-black/40 px-2.5 py-1 backdrop-blur">
              {showStorageLive ? "Cloud" : "Direct"}
            </span>
          ) : null}
        </div>

        {error ? (
          <p className="absolute inset-x-4 bottom-20 rounded-lg bg-black/70 px-3 py-2 text-center text-xs text-danger">
            {error}
          </p>
        ) : null}

        {active ? (
          <div className="absolute inset-x-0 bottom-0 flex items-center justify-between p-4">
            <button
              type="button"
              onClick={() => setMuted((v) => !v)}
              className="glass grid h-11 w-11 place-items-center rounded-full border border-white/10 text-white"
            >
              {muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
            </button>
            <button
              type="button"
              className="grid h-14 w-14 place-items-center rounded-full bg-gradient-gold text-gold-foreground shadow-gold"
            >
              <Volume2 className="h-5 w-5" />
            </button>
            <button
              type="button"
              className="glass grid h-11 w-11 place-items-center rounded-full border border-white/10 text-white"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
          </div>
        ) : null}
      </div>

      <div className="mt-5 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {loading ? (
          <p className="text-xs text-muted-foreground">Loading cameras…</p>
        ) : (
          devices.map((c) => {
            const isActive = c.id === active?.id;
            const live = c.status === "online" || (isActive && isLive);
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => setActive(c)}
                className={`shrink-0 rounded-full border px-4 py-2 text-xs transition ${
                  isActive
                    ? "border-transparent bg-gradient-gold text-gold-foreground shadow-gold"
                    : "border-border bg-card text-muted-foreground"
                }`}
              >
                <span
                  className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${live ? "bg-success" : "bg-muted-foreground"}`}
                />
                {c.name}
              </button>
            );
          })
        )}
      </div>

      <section className="mt-7">
        <h2 className="font-display text-2xl">Recordings</h2>
        {recordings.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">
            Clips appear here while the camera page is open and recording.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {recordings.map((r) => (
              <li key={r.id} className="flex items-center gap-3 rounded-2xl border border-border bg-card p-3">
                <a
                  href={r.publicUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="grid h-12 w-12 place-items-center rounded-xl bg-accent text-foreground"
                >
                  <Play className="h-4 w-4" />
                </a>
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate">{active?.name ?? "Camera"}</p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(r.createdAt).toLocaleString()}
                  </p>
                </div>
                {r.durationMs ? (
                  <span className="text-xs text-muted-foreground">
                    {Math.round(r.durationMs / 1000)}s
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function WaitingOverlay({ deviceName }: { deviceName: string }) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6 text-center">
      <Video className="h-8 w-8 animate-pulse text-gold" />
      <p className="text-sm text-white/80">Waiting for {deviceName}</p>
      <p className="text-xs text-white/50">Open the camera link on the phone and allow access</p>
    </div>
  );
}
