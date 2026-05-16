import { useEffect, useRef } from "react";
import { liveFeedStoragePath, publicStorageUrl, saveRecording, uploadLiveChunk } from "@/lib/devices";

const LIVE_INTERVAL_MS = 4000;
const CLIP_MS = 15000;

type UseCameraRecorderOptions = {
  deviceId: string;
  stream: MediaStream | null;
  enabled: boolean;
};

/** Records from the camera stream, uploads live chunks + saved clips to Supabase Storage. */
export function useCameraRecorder({ deviceId, stream, enabled }: UseCameraRecorderOptions) {
  const liveTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const clipTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const liveRecorder = useRef<MediaRecorder | null>(null);

  useEffect(() => {
    if (!enabled || !stream || !deviceId) return;

    const mime = MediaRecorder.isTypeSupported("video/webm;codecs=vp8")
      ? "video/webm;codecs=vp8"
      : "video/webm";

    const recordClip = () => {
      const chunks: Blob[] = [];
      const rec = new MediaRecorder(stream, { mimeType: mime });
      mediaRecorder.current = rec;
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };
      rec.onstop = () => {
        if (chunks.length === 0) return;
        const blob = new Blob(chunks, { type: mime });
        void saveRecording(deviceId, blob, CLIP_MS).catch(() => undefined);
      };
      rec.start();
      setTimeout(() => {
        if (rec.state === "recording") rec.stop();
      }, CLIP_MS);
    };

    const uploadLive = () => {
      const chunks: Blob[] = [];
      const rec = new MediaRecorder(stream, { mimeType: mime });
      liveRecorder.current = rec;
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };
      rec.onstop = () => {
        if (chunks.length === 0) return;
        const blob = new Blob(chunks, { type: mime });
        void uploadLiveChunk(deviceId, blob).catch(() => undefined);
      };
      rec.start();
      setTimeout(() => {
        if (rec.state === "recording") rec.stop();
      }, 2500);
    };

    recordClip();
    uploadLive();
    clipTimer.current = setInterval(recordClip, CLIP_MS);
    liveTimer.current = setInterval(uploadLive, LIVE_INTERVAL_MS);

    return () => {
      if (clipTimer.current) clearInterval(clipTimer.current);
      if (liveTimer.current) clearInterval(liveTimer.current);
      mediaRecorder.current?.state === "recording" && mediaRecorder.current.stop();
      liveRecorder.current?.state === "recording" && liveRecorder.current.stop();
    };
  }, [deviceId, stream, enabled]);

  return { liveFeedUrl: publicStorageUrl(liveFeedStoragePath(deviceId)) };
}
