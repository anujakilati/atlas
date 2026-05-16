import { Video, Minus } from "lucide-react";
import { useEffect, useState } from "react";
import type { Device, DeviceRecording } from "@/lib/devices";
import { DeviceLivePlayer } from "./DeviceLivePlayer";
import { supabase } from "@/lib/supabase";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.replace(/\/$/, "");
const SERVICE_KEY = import.meta.env.VITE_SUPABASE_SERVICE_KEY;

type Props = {
  active: Device | null;
  bubbleId: string;
  recordings: DeviceRecording[];
  muted: boolean;
  onMutedChange: (muted: boolean) => void;
  onDeleteRecording: (id: string, storagePath: string) => void;
  onDeleteDevice: (device: Device) => void;
  deletingId: string | null;
  deleteError: string | null;
  loading: boolean;
};

export function CameraIndividualView({
  active,
  bubbleId,
  recordings,
  muted,
  onMutedChange,
  onDeleteRecording,
  onDeleteDevice,
  deletingId,
  deleteError,
  loading,
}: Props) {
  const [locked, setLocked] = useState(false);
  const [lockMessage, setLockMessage] = useState<string | undefined>();

  // Subscribe to camera_lock / camera_unlock events via Supabase Realtime
  useEffect(() => {
    if (!active?.id) return;

    const channel = supabase
      .channel(`camera-lock-${active.id}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "device_events",
          filter: `device=eq.${active.id}`,
        },
        (payload) => {
          const row = payload.new as { event_type: string; metadata?: Record<string, unknown> };
          if (row.event_type === "camera_lock") {
            setLocked(true);
            setLockMessage((row.metadata?.message as string | undefined) ?? undefined);
          } else if (row.event_type === "camera_unlock") {
            setLocked(false);
            setLockMessage(undefined);
          }
        },
      )
      .subscribe();

    return () => {
      void supabase.removeChannel(channel);
    };
  }, [active?.id]);

  const handleUnlock = async () => {
    if (!active?.id || !SUPABASE_URL || !SERVICE_KEY) {
      setLocked(false);
      setLockMessage(undefined);
      return;
    }
    try {
      await fetch(`${SUPABASE_URL}/rest/v1/device_events`, {
        method: "POST",
        headers: {
          apikey: SERVICE_KEY,
          Authorization: `Bearer ${SERVICE_KEY}`,
          "Content-Type": "application/json",
          Prefer: "return=minimal",
        },
        body: JSON.stringify({
          bubble: bubbleId,
          device: active.id,
          event_type: "camera_unlock",
          incident_confirmed: false,
          metadata: { source: "operator", action: "manual_unlock" },
        }),
      });
    } catch {
      // optimistically unlock even if the insert fails
    }
    setLocked(false);
    setLockMessage(undefined);
  };

  return (
    <>
      <div
        className={`relative aspect-[4/5] overflow-hidden rounded-3xl border bg-black transition-colors ${
          locked ? "border-danger" : "border-border"
        }`}
      >
        {active ? (
          <DeviceLivePlayer
            key={active.id}
            deviceId={active.id}
            deviceName={active.name}
            deviceOnline={active.status === "online"}
            muted={muted}
            onMutedChange={onMutedChange}
            locked={locked}
            lockMessage={lockMessage}
            onUnlock={handleUnlock}
          />
        ) : null}

        {active && !locked ? (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <button
                type="button"
                className="absolute right-3 top-3 z-40 grid h-8 w-8 place-items-center rounded-full bg-black/40 text-white backdrop-blur hover:bg-destructive/80 transition-colors cursor-pointer"
                aria-label={`Delete ${active.name}`}
              >
                <Minus className="h-4 w-4" />
              </button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Disconnect camera?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will permanently remove <strong>{active.name}</strong> and all its recordings. This cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => onDeleteDevice(active)}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  Disconnect
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        ) : null}

        {!active && !loading ? (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-gradient-to-br from-zinc-900 via-zinc-800 to-black p-6 text-center">
            <Video className="h-10 w-10 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No cameras yet. Add a device and register it with a token.
            </p>
          </div>
        ) : null}
      </div>

    </>
  );
}
