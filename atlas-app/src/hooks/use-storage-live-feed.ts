import { useEffect, useState } from "react";
import { liveFeedStoragePath, publicStorageUrl } from "@/lib/devices";

/** Polls the latest uploaded live.webm chunk from Supabase Storage. */
export function useStorageLiveFeed(deviceId: string | null, enabled: boolean) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!deviceId || !enabled) {
      setSrc(null);
      return;
    }

    const base = publicStorageUrl(liveFeedStoragePath(deviceId));
    const refresh = () => setSrc(`${base}?t=${Date.now()}`);

    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [deviceId, enabled]);

  return src;
}
