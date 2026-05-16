import { Video } from "lucide-react";
import type { Device } from "@/lib/devices";
import { DeviceLivePlayer } from "./DeviceLivePlayer";

type Props = {
  devices: Device[];
  muted: boolean;
  onMutedChange: (muted: boolean) => void;
};

export function CameraGridView({ devices, muted, onMutedChange }: Props) {
  if (devices.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-3xl border border-border bg-card p-12 text-center">
        <Video className="h-10 w-10 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">No cameras yet. Add a device and register it with a token.</p>
      </div>
    );
  }

  return (
    <div className={`grid gap-3 ${devices.length === 1 ? "grid-cols-1" : "grid-cols-2"}`}>
      {devices.map((device) => (
        <div key={device.id} className="flex flex-col gap-1">
          <div className="relative aspect-[4/3] overflow-hidden rounded-2xl border border-border bg-black">
            <DeviceLivePlayer
              deviceId={device.id}
              deviceName={device.name}
              deviceOnline={device.status === "online"}
              muted={muted}
              onMutedChange={onMutedChange}
              showControls={false}
            />
          </div>
          <p className="truncate px-1 text-xs text-muted-foreground">{device.name}</p>
        </div>
      ))}
    </div>
  );
}
