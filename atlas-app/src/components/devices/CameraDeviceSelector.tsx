import type { Device } from "@/lib/devices";

type Props = {
  devices: Device[];
  activeId: string | null;
  onSelect: (device: Device) => void;
  loading: boolean;
};

export function CameraDeviceSelector({ devices, activeId, onSelect, loading }: Props) {
  if (loading) {
    return <p className="text-xs text-muted-foreground">Loading cameras…</p>;
  }

  return (
    <div className="flex gap-2 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {devices.map((device) => {
        const isActive = device.id === activeId;
        const live = device.status === "online";
        return (
          <button
            key={device.id}
            type="button"
            onClick={() => onSelect(device)}
            className={`flex shrink-0 items-center gap-1.5 rounded-full border px-4 py-2 text-xs transition ${
              isActive
                ? "border-transparent bg-gradient-gold text-gold-foreground shadow-gold"
                : "border-border bg-card text-muted-foreground"
            }`}
          >
            <span
              className={`inline-block h-1.5 w-1.5 rounded-full ${live ? "bg-success" : "bg-muted-foreground"}`}
            />
            {device.name}
          </button>
        );
      })}
    </div>
  );
}
