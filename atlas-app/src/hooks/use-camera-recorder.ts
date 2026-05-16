import { useEffect, useRef } from "react";
import { saveRecording, uploadLiveChunk } from "@/lib/devices";

const LIVE_INTERVAL_MS = 8000;
const CLIP_MS = 20000;

type UseCameraRecorderOptions = {
  deviceId: string;
  stream: MediaStream | null;
  enabled: boolean;
  /** Save 20s clips to activity — only when someone is watching */
  saveClips?: boolean;
};

/**
 * Records using a cloned stream so MediaRecorder does not steal tracks from WebRTC.
 * Live chunks (every ~8s) are a storage fallback when WebRTC is slow; clips are optional.
 */
export function useCameraRecorder({
  deviceId,
  stream,
  enabled,
}: UseCameraRecorderOptions) {
  const liveTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!enabled || !stream || !deviceId) return;

    const recordStream = stream.clone();
    const mime = MediaRecorder.isTypeSupported("video/webm;codecs=vp8")
      ? "video/webm;codecs=vp8"
      : "video/webm";

    const recordOnce = (durationMs: number, onBlob: (blob: Blob) => void) => {
      if (recordStream.getVideoTracks().length === 0) return;
      const chunks: Blob[] = [];
      const rec = new MediaRecorder(recordStream, { mimeType: mime, videoBitsPerSecond: 500_000 });
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };
      rec.onstop = () => {
        if (chunks.length === 0) return;
        onBlob(new Blob(chunks, { type: mime }));
      };
      rec.start(250);
      setTimeout(() => {
        if (rec.state === "recording") rec.stop();
      }, durationMs);
    };

    const uploadLive = () =>
      recordOnce(3000, (blob) => void uploadLiveChunk(deviceId, blob).catch(() => undefined));

    const startDelay = setTimeout(() => {
      void uploadLive();
      liveTimer.current = setInterval(uploadLive, LIVE_INTERVAL_MS);
    }, 2000);

    return () => {
      clearTimeout(startDelay);
      if (liveTimer.current) clearInterval(liveTimer.current);
      recordStream.getTracks().forEach((t) => t.stop());
    };
  }, [deviceId, stream, enabled]);

  const saveNow = async (title?: string) => {
    if (!enabled || !stream || !deviceId) return;
    const recordStream = stream.clone();
    const mime = MediaRecorder.isTypeSupported("video/webm;codecs=vp8")
      ? "video/webm;codecs=vp8"
      : "video/webm";

    await new Promise<void>((resolve) => {
      const chunks: Blob[] = [];
      const rec = new MediaRecorder(recordStream, { mimeType: mime, videoBitsPerSecond: 500_000 });
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };
      rec.onstop = async () => {
        if (chunks.length === 0) return resolve();
        try {
          await saveRecording(deviceId, new Blob(chunks, { type: mime }), CLIP_MS, title ?? "");
        } catch (e) {
          // swallow; caller can log if needed
          // eslint-disable-next-line no-console
          console.error("saveNow error:", e);
        }
        resolve();
      };
      rec.start(250);
      setTimeout(() => {
        if (rec.state === "recording") rec.stop();
      }, CLIP_MS);
    });
  };

  return { saveNow };
}
