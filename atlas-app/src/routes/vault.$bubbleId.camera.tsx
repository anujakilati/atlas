import { createFileRoute } from "@tanstack/react-router";
import { Play, Video, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  fetchBubbleDevices,
  fetchDeviceRecordings,
  deleteRecording,
  type Device,
  type DeviceRecording,
} from "@/lib/devices";
import { DeviceLivePlayer } from "@/components/devices/DeviceLivePlayer";

export const Route = createFileRoute("/vault/$bubbleId/camera")({
  component: CameraPage,
  head: () => ({
    meta: [
      { title: "Live View — Vault" },
      { name: "description", content: "Live camera feeds and past recordings from your home." },
    ],
  }),
});

function pickActiveDevice(list: Device[], prev: Device | null): Device | null {
  if (prev && list.some((d) => d.id === prev.id)) return prev;
  return list.find((d) => d.status === "online") ?? list[0] ?? null;
}

function CameraPage() {
  const { bubbleId } = Route.useParams();
  const [devices, setDevices] = useState<Device[]>([]);
  const [recordings, setRecordings] = useState<DeviceRecording[]>([]);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState<Device | null>(null);
  const [muted, setMuted] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const refreshDevices = useCallback(() => {
    void fetchBubbleDevices(bubbleId)
      .then((list) => {
        setDevices(list);
        setActive((prev) => pickActiveDevice(list, prev));
      })
      .catch(() => setDevices([]))
      .finally(() => setLoading(false));
  }, [bubbleId]);

  useEffect(() => {
    refreshDevices();
    const onFocus = () => refreshDevices();
    window.addEventListener("focus", onFocus);
    const id = setInterval(refreshDevices, 30000);
    return () => {
      window.removeEventListener("focus", onFocus);
      clearInterval(id);
    };
  }, [refreshDevices]);

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

  const handleDeleteRecording = async (recordingId: string, storagePath: string) => {
    setDeletingId(recordingId);
    setDeleteError(null);
    try {
      await deleteRecording(recordingId, storagePath);
      setRecordings((prev) => prev.filter((r) => r.id !== recordingId));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete recording";
      console.error("Delete recording error:", error);
      setDeleteError(message);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="px-5 pt-12">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Live view</p>
        <h1 className="mt-1 font-display text-3xl">{active?.name ?? "Cameras"}</h1>
        {active ? <p className="mt-0.5 text-sm text-muted-foreground">{active.placement}</p> : null}
      </header>

      <div className="relative mt-5 aspect-[4/5] overflow-hidden rounded-3xl border border-border bg-black">
        {active ? (
          <DeviceLivePlayer
            key={active.id}
            deviceId={active.id}
            deviceName={active.name}
            deviceOnline={active.status === "online"}
            muted={muted}
            onMutedChange={setMuted}
          />
        ) : null}

        {(!active && !loading) ? (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-gradient-to-br from-zinc-900 via-zinc-800 to-black p-6 text-center">
            <Video className="h-10 w-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No cameras yet. Add a device and register it with a token.
            </p>
          </div>
        ) : null}
      </div>

      <div className="mt-5 flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {loading ? (
          <p className="text-xs text-muted-foreground">Loading cameras…</p>
        ) : (
          devices.map((c) => {
            const isActive = c.id === active?.id;
            const live = c.status === "online";
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

      {devices.length > 1 ? (
        <p className="mt-2 text-center text-xs text-muted-foreground">
          Each camera needs its own device tab open with its token. Only one camera per browser.
        </p>
      ) : null}

      <section className="mt-7">
        <h2 className="font-display text-2xl">Recordings</h2>
        {deleteError ? (
          <div className="mt-3 rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            {deleteError}
          </div>
        ) : null}
        {recordings.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">
            Clips appear here while the device camera is streaming.
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
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{active?.name ?? "Camera"}</p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(r.createdAt).toLocaleString()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {r.durationMs ? (
                    <span className="text-xs text-muted-foreground">
                      {Math.round(r.durationMs / 1000)}s
                    </span>
                  ) : null}
                  <button
                    onClick={() => handleDeleteRecording(r.id, r.storagePath)}
                    disabled={deletingId === r.id}
                    className="p-2 text-muted-foreground hover:text-destructive disabled:opacity-50 transition-colors"
                    aria-label="Delete recording"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
