import { useEffect, useState } from "react";
import { fetchDeviceRecordings, liveFeedStoragePath, publicStorageUrl } from "@/lib/devices";

/**
 * Cloud fallback when WebRTC has no frames yet.
 * Uses the latest saved clip (valid webm) first; falls back to live.webm chunk.
 */
export function useStorageLiveFeed(deviceId: string | null, enabled: boolean) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!deviceId || !enabled) {
      setSrc(null);
      return;
    }

    const refresh = async () => {
      const cacheBust = Date.now();
      try {
        const recordings = await fetchDeviceRecordings(deviceId);
        if (recordings[0]?.publicUrl) {
          setSrc(`${recordings[0].publicUrl}?t=${cacheBust}`);
          return;
        }
      } catch {
        // fall through to live chunk
      }
      const liveUrl = publicStorageUrl(liveFeedStoragePath(deviceId));
      setSrc(`${liveUrl}?t=${cacheBust}`);
    };

    void refresh();
    const id = setInterval(() => void refresh(), 5000);
    return () => clearInterval(id);
  }, [deviceId, enabled]);

  return src;
}
