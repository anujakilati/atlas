import { useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";

const ICE_SERVERS: RTCIceServer[] = [{ urls: "stun:stun.l.google.com:19302" }];

type SignalPayload =
  | { type: "offer"; sdp: string }
  | { type: "answer"; sdp: string }
  | { type: "ice"; candidate: RTCIceCandidateInit }
  | { type: "viewer-ready" };

export function useDeviceStream(deviceId: string | null, role: "broadcaster" | "viewer") {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [connected, setConnected] = useState(false);
  const [waiting, setWaiting] = useState(role === "viewer");
  const [error, setError] = useState<string | null>(null);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);

  useEffect(() => {
    if (!deviceId) return;

    let disposed = false;
    let mediaStream: MediaStream | null = null;
    const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });

    const channel = supabase.channel(`device-stream:${deviceId}`, {
      config: { broadcast: { ack: false } },
    });

    const sendSignal = (payload: SignalPayload) => {
      void channel.send({ type: "broadcast", event: "signal", payload });
    };

    pc.onicecandidate = (event) => {
      if (event.candidate) {
        sendSignal({ type: "ice", candidate: event.candidate.toJSON() });
      }
    };

    pc.ontrack = (event) => {
      const stream = event.streams[0];
      if (stream && videoRef.current) {
        videoRef.current.srcObject = stream;
        void videoRef.current.play().catch(() => undefined);
      }
      setConnected(true);
      setWaiting(false);
    };

    pc.onconnectionstatechange = () => {
      if (pc.connectionState === "connected") {
        setConnected(true);
        setWaiting(false);
      }
      if (pc.connectionState === "failed") {
        setError("Connection failed. Keep the pairing page open and try again.");
      }
    };

    const resendOffer = () => {
      const sdp = pc.localDescription?.sdp;
      if (sdp) sendSignal({ type: "offer", sdp });
    };

    channel.on("broadcast", { event: "signal" }, async ({ payload }) => {
      if (disposed) return;
      const msg = payload as SignalPayload;

      try {
        if (msg.type === "viewer-ready" && role === "broadcaster") {
          resendOffer();
        } else if (msg.type === "offer" && role === "viewer") {
          await pc.setRemoteDescription({ type: "offer", sdp: msg.sdp });
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);
          sendSignal({ type: "answer", sdp: answer.sdp ?? "" });
        } else if (msg.type === "answer" && role === "broadcaster") {
          await pc.setRemoteDescription({ type: "answer", sdp: msg.sdp });
        } else if (msg.type === "ice" && msg.candidate) {
          await pc.addIceCandidate(msg.candidate);
        }
      } catch {
        // ICE/SDP can race during setup
      }
    });

    const start = async () => {
      try {
        if (role === "broadcaster") {
          mediaStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: "environment" } },
            audio: true,
          });
          if (disposed) return;

          if (videoRef.current) {
            videoRef.current.srcObject = mediaStream;
            videoRef.current.muted = true;
            void videoRef.current.play().catch(() => undefined);
          }

          setLocalStream(mediaStream);
          mediaStream.getTracks().forEach((track) => pc.addTrack(track, mediaStream!));
          const offer = await pc.createOffer();
          await pc.setLocalDescription(offer);
          sendSignal({ type: "offer", sdp: offer.sdp ?? "" });
          setWaiting(false);
        }
      } catch (err) {
        setError(
          err instanceof Error && err.name === "NotAllowedError"
            ? "Camera permission is required to stream."
            : "Could not access camera.",
        );
      }
    };

    void channel.subscribe((status) => {
      if (status === "SUBSCRIBED" && !disposed) {
        if (role === "viewer") {
          sendSignal({ type: "viewer-ready" });
        }
        void start();
      }
    });

    return () => {
      disposed = true;
      mediaStream?.getTracks().forEach((t) => t.stop());
      setLocalStream(null);
      pc.close();
      void supabase.removeChannel(channel);
    };
  }, [deviceId, role]);

  return { videoRef, connected, waiting, error, localStream };
}
