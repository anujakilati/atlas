import { Mic, MicOff, Volume2, Maximize2, Circle, Video, Lock, Unlock } from "lucide-react";
import { useDeviceStream } from "@/hooks/use-device-stream";
import { useStorageLiveFeed } from "@/hooks/use-storage-live-feed";

type DeviceLivePlayerProps = {
  deviceId: string;
  deviceName: string;
  deviceOnline: boolean;
  muted: boolean;
  onMutedChange: (muted: boolean) => void;
  showControls?: boolean;
  locked?: boolean;
  lockMessage?: string;
  onUnlock?: () => void;
};

/** Key by deviceId so switching cameras fully resets WebRTC. */
export function DeviceLivePlayer({
  deviceId,
  deviceName,
  deviceOnline,
  muted,
  onMutedChange,
  showControls = true,
  locked = false,
  lockMessage = "Locked by Guardian AI — suspicious activity detected",
  onUnlock,
}: DeviceLivePlayerProps) {
  const { videoRef, hasMedia, waiting, error } = useDeviceStream(deviceId, "viewer");
  const storageLiveSrc = useStorageLiveFeed(deviceId, deviceOnline && !hasMedia);

  const showWebRtc = hasMedia;
  const showStorage = !showWebRtc && deviceOnline && Boolean(storageLiveSrc);
  const showVideo = showWebRtc || showStorage;
  const showWaitingOverlay = waiting && !showVideo;

  return (
    <>
      <video
        ref={videoRef}
        playsInline
        autoPlay
        muted={muted}
        className={`absolute inset-0 h-full w-full object-cover ${showWebRtc ? "z-20" : "z-0 hidden"}`}
      />

      {showStorage ? (
        <video
          key={storageLiveSrc}
          src={storageLiveSrc ?? undefined}
          playsInline
          autoPlay
          muted={muted}
          className="absolute inset-0 z-10 h-full w-full object-cover"
          onLoadedData={(e) => void e.currentTarget.play().catch(() => undefined)}
        />
      ) : null}

      {showWaitingOverlay ? (
        <div className="absolute inset-0 z-20 bg-gradient-to-br from-zinc-900 via-zinc-800 to-black">
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6 text-center">
            <Video className="h-8 w-8 animate-pulse text-gold" />
            <p className="text-sm text-white/80">Connecting to {deviceName}…</p>
            <p className="text-xs text-white/50">Reconnects automatically — or tap ↻</p>
          </div>
        </div>
      ) : null}

      {showVideo ? (
        <div className="scan-line pointer-events-none absolute inset-x-0 z-30 h-px bg-gold/60" />
      ) : null}

      <div className="absolute inset-x-0 top-0 z-30 flex items-center p-4 text-xs text-white/80">
        {showWebRtc ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-black/40 px-2.5 py-1 backdrop-blur">
            <Circle className="h-2 w-2 fill-danger text-danger" /> LIVE
          </span>
        ) : showStorage ? (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-black/40 px-2.5 py-1 backdrop-blur">
            <Circle className="h-2 w-2 fill-danger text-danger" /> LIVE · cloud
          </span>
        ) : (
          <span className="rounded-full bg-black/40 px-2.5 py-1 backdrop-blur text-muted-foreground">
            {deviceOnline ? "Connecting…" : "Offline"}
          </span>
        )}
      </div>

      {error ? (
        <p className="absolute inset-x-4 bottom-20 z-30 rounded-lg bg-black/70 px-3 py-2 text-center text-xs text-danger">
          {error}
        </p>
      ) : null}

      {showControls && !locked ? (
        <div className="absolute inset-x-0 bottom-0 z-30 flex items-center justify-between p-4">
          <button
            type="button"
            onClick={() => onMutedChange(!muted)}
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

      {locked ? (
        <div className="absolute inset-0 z-40 flex flex-col items-center justify-center gap-3 rounded-[inherit] border-2 border-danger bg-black/70 p-6 text-center backdrop-blur-sm">
          <span className="grid h-14 w-14 place-items-center rounded-full bg-danger/20 text-danger">
            <Lock className="h-6 w-6" />
          </span>
          <p className="text-sm font-medium text-white">{lockMessage}</p>
          {onUnlock ? (
            <button
              type="button"
              onClick={onUnlock}
              className="mt-1 flex items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-xs text-white transition hover:bg-white/20"
            >
              <Unlock className="h-3.5 w-3.5" />
              Unlock camera
            </button>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
