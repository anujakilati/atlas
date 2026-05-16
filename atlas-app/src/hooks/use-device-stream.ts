import { useCallback, useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";

const ICE_SERVERS: RTCIceServer[] = [
  { urls: "stun:stun.l.google.com:19302" },
  { urls: "stun:stun1.l.google.com:19302" },
];

type SignalPayload =
  | { type: "offer"; sdp: string }
  | { type: "answer"; sdp: string }
  | { type: "ice"; candidate: RTCIceCandidateInit }
  | { type: "viewer-ready" };

function preferCameraConstraints(): MediaStreamConstraints {
  const isMobile = /iPhone|iPad|Android/i.test(navigator.userAgent);
  return {
    video: isMobile ? { facingMode: { ideal: "environment" } } : true,
    audio: true,
  };
}

export function useDeviceStream(deviceId: string | null, role: "broadcaster" | "viewer") {
  const videoRef = useRef<HTMLVideoElement>(null);
  const remoteStreamRef = useRef<MediaStream | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const [viewerWatching, setViewerWatching] = useState(false);
  const [hasMedia, setHasMedia] = useState(false);
  const [waiting, setWaiting] = useState(role === "viewer");
  const [error, setError] = useState<string | null>(null);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);

  const attachToVideo = useCallback((stream: MediaStream | null) => {
    const el = videoRef.current;
    if (!el || !stream) return;
    if (el.srcObject !== stream) {
      el.srcObject = stream;
    }
    void el.play().catch(() => undefined);
  }, []);

  const setVideoRef = useCallback(
    (el: HTMLVideoElement | null) => {
      videoRef.current = el;
      if (!el) return;
      const stream = role === "viewer" ? remoteStreamRef.current : localStreamRef.current;
      if (stream) attachToVideo(stream);
    },
    [attachToVideo, role],
  );

  useEffect(() => {
    if (!deviceId) return;

    setHasMedia(false);
    setViewerWatching(false);
    setWaiting(role === "viewer");
    setError(null);
    remoteStreamRef.current = null;

    let disposed = false;
    let generation = 0;
    let viewerReadyTimer: ReturnType<typeof setInterval> | null = null;
    let disconnectTimer: ReturnType<typeof setTimeout> | null = null;
    const pendingIce: RTCIceCandidateInit[] = [];
    const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });

    const streamIsUp = () => {
      const ice = pc.iceConnectionState;
      return (
        pc.connectionState === "connected" ||
        ice === "connected" ||
        ice === "completed"
      );
    };

    const drainIce = async () => {
      if (!pc.remoteDescription) return;
      while (pendingIce.length > 0) {
        const candidate = pendingIce.shift()!;
        try {
          await pc.addIceCandidate(new RTCIceCandidate(candidate));
        } catch {
          // stale candidate after renegotiation
        }
      }
    };

    const queueIce = (candidate: RTCIceCandidateInit) => {
      if (pc.remoteDescription) {
        void pc.addIceCandidate(new RTCIceCandidate(candidate)).catch(() => undefined);
      } else {
        pendingIce.push(candidate);
      }
    };

    const stopViewerReadyPing = () => {
      if (viewerReadyTimer) {
        clearInterval(viewerReadyTimer);
        viewerReadyTimer = null;
      }
    };

    const markBroadcasterViewerJoined = () => {
      if (disconnectTimer) {
        clearTimeout(disconnectTimer);
        disconnectTimer = null;
      }
      setViewerWatching(true);
      setWaiting(false);
      setError(null);
    };

    const markViewerStreamReady = (stream: MediaStream) => {
      if (disconnectTimer) {
        clearTimeout(disconnectTimer);
        disconnectTimer = null;
      }
      remoteStreamRef.current = stream;
      attachToVideo(stream);
      setHasMedia(true);
      setViewerWatching(true);
      setWaiting(false);
      setError(null);
      stopViewerReadyPing();
    };

    const markViewerDisconnected = () => {
      setViewerWatching(false);
    };

    const scheduleDisconnect = () => {
      if (role === "broadcaster") return;
      if (disconnectTimer) clearTimeout(disconnectTimer);
      disconnectTimer = setTimeout(() => {
        if (!streamIsUp()) {
          markViewerDisconnected();
          setHasMedia(false);
          remoteStreamRef.current = null;
          setWaiting(true);
          if (!disposed && !viewerReadyTimer) {
            sendSignal({ type: "viewer-ready" });
            viewerReadyTimer = setInterval(() => sendSignal({ type: "viewer-ready" }), 4000);
          }
        }
      }, 4000);
    };

    const channel = supabase.channel(`device-stream:${deviceId}`, {
      config: { broadcast: { ack: false } },
    });

    const sendSignal = (payload: SignalPayload) => {
      if (disposed) return;
      void channel.send({ type: "broadcast", event: "signal", payload });
    };

    pc.onicecandidate = (event) => {
      if (event.candidate) {
        sendSignal({ type: "ice", candidate: event.candidate.toJSON() });
      }
    };

    pc.ontrack = (event) => {
      const stream = event.streams[0] ?? (event.track ? new MediaStream([event.track]) : null);
      if (!stream || role !== "viewer") return;
      markViewerStreamReady(stream);
    };

    pc.onconnectionstatechange = () => {
      const state = pc.connectionState;
      if (state === "failed" || state === "closed") {
        if (disconnectTimer) {
          clearTimeout(disconnectTimer);
          disconnectTimer = null;
        }
        if (role === "broadcaster") {
          markViewerDisconnected();
        } else {
          markViewerDisconnected();
          setHasMedia(false);
          remoteStreamRef.current = null;
          setWaiting(true);
          setError("Connection lost. Keep the device camera page open and refresh Live view.");
          if (!disposed) {
            stopViewerReadyPing();
            sendSignal({ type: "viewer-ready" });
            viewerReadyTimer = setInterval(() => sendSignal({ type: "viewer-ready" }), 4000);
          }
        }
      } else if (state === "disconnected") {
        scheduleDisconnect();
      }
    };

    const applyOffer = async (sdp: string) => {
      const gen = generation;
      if (streamIsUp()) return;
      await pc.setRemoteDescription({ type: "offer", sdp });
      if (disposed || gen !== generation) return;
      await drainIce();
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      sendSignal({ type: "answer", sdp: answer.sdp ?? "" });
    };

    const applyAnswer = async (sdp: string) => {
      const gen = generation;
      if (pc.signalingState !== "have-local-offer") return;
      await pc.setRemoteDescription({ type: "answer", sdp });
      if (disposed || gen !== generation) return;
      await drainIce();
      markBroadcasterViewerJoined();
    };

    const resendOffer = async () => {
      const gen = generation;
      if (streamIsUp()) return;
      const localSdp = pc.localDescription?.sdp;
      if (localSdp && pc.signalingState === "have-local-offer") {
        sendSignal({ type: "offer", sdp: localSdp });
        return;
      }
      const offer = await pc.createOffer(
        pc.signalingState === "stable" ? { iceRestart: true } : undefined,
      );
      await pc.setLocalDescription(offer);
      if (disposed || gen !== generation) return;
      sendSignal({ type: "offer", sdp: offer.sdp ?? "" });
    };

    channel.on("broadcast", { event: "signal" }, async ({ payload }) => {
      if (disposed) return;
      const msg = payload as SignalPayload;

      try {
        if (msg.type === "viewer-ready" && role === "broadcaster") {
          if (streamIsUp()) return;
          await resendOffer();
        } else if (msg.type === "offer" && role === "viewer") {
          if (streamIsUp()) return;
          await applyOffer(msg.sdp);
        } else if (msg.type === "answer" && role === "broadcaster") {
          await applyAnswer(msg.sdp);
        } else if (msg.type === "ice" && msg.candidate) {
          queueIce(msg.candidate);
        }
      } catch {
        // SDP/ICE can race during setup; viewer-ready will retry
      }
    });

    const startBroadcaster = async () => {
      try {
        const mediaStream = await navigator.mediaDevices.getUserMedia(preferCameraConstraints());
        if (disposed) {
          mediaStream.getTracks().forEach((t) => t.stop());
          return;
        }

        localStreamRef.current = mediaStream;
        setLocalStream(mediaStream);
        setHasMedia(true);
        attachToVideo(mediaStream);

        mediaStream.getTracks().forEach((track) => pc.addTrack(track, mediaStream));
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        sendSignal({ type: "offer", sdp: offer.sdp ?? "" });
        setWaiting(false);
      } catch (err) {
        setError(
          err instanceof Error && err.name === "NotAllowedError"
            ? "Camera permission is required to stream."
            : "Could not access camera.",
        );
      }
    };

    void channel.subscribe((status) => {
      if (status !== "SUBSCRIBED" || disposed) return;

      if (role === "viewer") {
        sendSignal({ type: "viewer-ready" });
        viewerReadyTimer = setInterval(() => sendSignal({ type: "viewer-ready" }), 4000);
      } else {
        void startBroadcaster();
      }
    });

    return () => {
      disposed = true;
      generation += 1;
      stopViewerReadyPing();
      if (disconnectTimer) clearTimeout(disconnectTimer);
      localStreamRef.current?.getTracks().forEach((t) => t.stop());
      localStreamRef.current = null;
      remoteStreamRef.current = null;
      setLocalStream(null);
      setHasMedia(false);
      setViewerWatching(false);
      pc.close();
      void channel.unsubscribe();
      void supabase.removeChannel(channel);
    };
  }, [deviceId, role, attachToVideo]);

  return {
    videoRef: setVideoRef,
    connected: viewerWatching,
    viewerWatching,
    hasMedia,
    waiting,
    error,
    localStream,
  };
}
