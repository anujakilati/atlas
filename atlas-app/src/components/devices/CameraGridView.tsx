import type { Device } from "@/lib/devices";
import { DeviceLivePlayer } from "./DeviceLivePlayer";
import { SimulationGrid } from "./SimulationGrid";

type Props = {
  devices: Device[];
  muted: boolean;
  onMutedChange: (muted: boolean) => void;
};

export function CameraGridView({ devices, muted, onMutedChange }: Props) {
  const realDevices = devices.filter((d) => !d.name.startsWith("Sim Cam "));
  if (realDevices.length === 0) {
    return <SimulationGrid />;
  }

  return (
    <div className={`grid gap-3 ${realDevices.length === 1 ? "grid-cols-1" : "grid-cols-2"}`}>
      {realDevices.map((device) => (
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
