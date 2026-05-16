import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Circle, Video, AlertCircle, LogOut } from "lucide-react";
import { useEffect } from "react";
import { clearDeviceSession, getDeviceSession } from "@/lib/device-session";
import { setDeviceStatusByToken } from "@/lib/devices";
import { useDeviceStream } from "@/hooks/use-device-stream";
import { useCameraRecorder } from "@/hooks/use-camera-recorder";

export const Route = createFileRoute("/device/live")({
  component: DeviceLivePage,
  head: () => ({
    meta: [{ title: "Vault — Live camera" }],
  }),
});

function DeviceLivePage() {
  const navigate = useNavigate();
  const session = getDeviceSession();

  useEffect(() => {
    if (!getDeviceSession()) {
      void navigate({ to: "/device", replace: true });
    }
  }, [navigate]);

  const deviceId = session?.deviceId ?? null;
  const { videoRef, connected, error: streamError, localStream } = useDeviceStream(deviceId, "broadcaster");

  useCameraRecorder({
    deviceId: deviceId ?? "",
    stream: localStream,
    enabled: Boolean(localStream && connected && deviceId),
  });

  useEffect(() => {
    if (!connected || !session?.token) return;
    void setDeviceStatusByToken(session.token, "online");
    return () => {
      void setDeviceStatusByToken(session.token, "offline");
    };
  }, [connected, session?.token]);

  const disconnect = () => {
    if (session?.token) void setDeviceStatusByToken(session.token, "offline");
    clearDeviceSession();
    void navigate({ to: "/device", replace: true });
  };

  if (!session) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  const displayError = streamError ?? null;

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="flex items-center justify-between px-5 pt-12">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{session.bubbleName}</p>
          <h1 className="font-display text-2xl">{session.name}</h1>
          <p className="text-xs text-muted-foreground">{session.placement}</p>
        </div>
        <button
          type="button"
          onClick={disconnect}
          className="grid h-10 w-10 place-items-center rounded-full border border-border text-muted-foreground"
          aria-label="Disconnect device"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </header>

      <div className="relative mx-5 mt-4 flex-1 overflow-hidden rounded-3xl border border-border bg-black">
        <video
          ref={videoRef}
          playsInline
          autoPlay
          muted
          className="absolute inset-0 h-full w-full object-cover"
        />
        {!connected && !displayError ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/70 p-6 text-center">
            <Video className="h-10 w-10 text-gold" />
            <p className="text-sm text-white/80">Allow camera to go live</p>
          </div>
        ) : null}
        {connected ? (
          <div className="absolute left-4 top-4 inline-flex items-center gap-1.5 rounded-full bg-black/50 px-2.5 py-1 text-xs text-white backdrop-blur">
            <Circle className="h-2 w-2 fill-danger text-danger" />
            LIVE
          </div>
        ) : null}
      </div>

      <div className="px-5 py-5">
        {displayError ? (
          <p className="flex items-start gap-2 text-sm text-danger">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            {displayError}
          </p>
        ) : (
          <p className="text-center text-sm text-muted-foreground">
            {connected
              ? "Streaming to your bubble. Keep this app open."
              : "Camera-only mode — no other features on this device."}
          </p>
        )}
      </div>
    </div>
  );
}
