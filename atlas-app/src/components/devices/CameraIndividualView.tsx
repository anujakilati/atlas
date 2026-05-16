import { Play, Trash2, Video, Minus } from "lucide-react";
import type { Device, DeviceRecording } from "@/lib/devices";
import { DeviceLivePlayer } from "./DeviceLivePlayer";
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

type Props = {
  active: Device | null;
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
  recordings,
  muted,
  onMutedChange,
  onDeleteRecording,
  onDeleteDevice,
  deletingId,
  deleteError,
  loading,
}: Props) {
  return (
    <>
      <div className="relative aspect-[4/5] overflow-hidden rounded-3xl border border-border bg-black">
        {active ? (
          <DeviceLivePlayer
            key={active.id}
            deviceId={active.id}
            deviceName={active.name}
            deviceOnline={active.status === "online"}
            muted={muted}
            onMutedChange={onMutedChange}
          />
        ) : null}

        {active ? (
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
                    onClick={() => onDeleteRecording(r.id, r.storagePath)}
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
    </>
  );
}
