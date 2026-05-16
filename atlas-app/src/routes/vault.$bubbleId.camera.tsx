import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import {
  fetchBubbleDevices,
  fetchDeviceRecordings,
  deleteRecording,
  deleteDevice,
  type Device,
  type DeviceRecording,
} from "@/lib/devices";
import { CameraDeviceSelector } from "@/components/devices/CameraDeviceSelector";
import { CameraIndividualView } from "@/components/devices/CameraIndividualView";
import { CameraGridView } from "@/components/devices/CameraGridView";
import { YoloWatchView } from "@/components/devices/YoloWatchView";

export const Route = createFileRoute("/vault/$bubbleId/camera")({
  component: CameraPage,
  head: () => ({
    meta: [
      { title: "Live View — Vault" },
      { name: "description", content: "Live camera feeds and past recordings from your home." },
    ],
  }),
});

type Tab = "individual" | "full" | "ai-watch";

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
  const [tab, setTab] = useState<Tab>("individual");
  const [deletingRecordingId, setDeletingRecordingId] = useState<string | null>(null);
  const [deleteRecordingError, setDeleteRecordingError] = useState<string | null>(null);
  const [deletingDeviceId, setDeletingDeviceId] = useState<string | null>(null);

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
    setDeletingRecordingId(recordingId);
    setDeleteRecordingError(null);
    try {
      await deleteRecording(recordingId, storagePath);
      setRecordings((prev) => prev.filter((r) => r.id !== recordingId));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to delete recording";
      setDeleteRecordingError(message);
    } finally {
      setDeletingRecordingId(null);
    }
  };

  const handleDeleteDevice = async (device: Device) => {
    setDeletingDeviceId(device.id);
    try {
      await deleteDevice(device.id, bubbleId);
      setDevices((prev) => {
        const next = prev.filter((d) => d.id !== device.id);
        setActive((prevActive) => pickActiveDevice(next, prevActive?.id === device.id ? null : prevActive));
        return next;
      });
    } catch (error) {
      console.error("Delete device error:", error);
    } finally {
      setDeletingDeviceId(null);
    }
  };

  return (
    <div className="px-5 pt-12">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Live view</p>
        <h1 className="mt-1 font-display text-3xl">
          {tab === "individual" ? (active?.name ?? "Cameras") : tab === "ai-watch" ? "AI Watch" : "All Cameras"}
        </h1>
        {tab === "individual" && active ? (
          <p className="mt-0.5 text-sm text-muted-foreground">{active.placement}</p>
        ) : null}
      </header>

      <div className="mt-5 flex gap-2">
        {(["individual", "full", "ai-watch"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`cursor-pointer rounded-full border px-4 py-1.5 text-xs transition ${
              tab === t
                ? "border-transparent bg-gradient-gold text-gold-foreground shadow-gold"
                : "border-border bg-card text-muted-foreground"
            }`}
          >
            {t === "individual" ? "Individual Live Feed" : t === "full" ? "Full View" : "AI Watch"}
          </button>
        ))}
      </div>

      <div className="mt-5">
        {tab === "individual" ? (
          <CameraIndividualView
            active={active}
            bubbleId={bubbleId}
            recordings={recordings}
            muted={muted}
            onMutedChange={setMuted}
            onDeleteRecording={handleDeleteRecording}
            onDeleteDevice={handleDeleteDevice}
            deletingId={deletingRecordingId}
            deleteError={deleteRecordingError}
            loading={loading}
          />
        ) : tab === "ai-watch" ? (
          <YoloWatchView />
        ) : (
          <CameraGridView devices={devices} muted={muted} onMutedChange={setMuted} />
        )}
      </div>

      {tab !== "ai-watch" && (
        <div className="mt-5">
          <CameraDeviceSelector
            devices={devices}
            activeId={active?.id ?? null}
            onSelect={setActive}
            loading={loading || deletingDeviceId !== null}
          />
        </div>
      )}

      {devices.length > 1 && tab !== "ai-watch" ? (
        <p className="mt-2 text-center text-xs text-muted-foreground">
          Each camera needs its own device tab open with its token. Only one camera per browser.
        </p>
      ) : null}
    </div>
  );
}
