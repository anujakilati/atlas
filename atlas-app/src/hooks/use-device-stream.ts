import { useCallback, useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";

const ICE_SERVERS: RTCIceServer[] = [
  { urls: "stun:stun.l.google.com:19302" },
  { urls: "stun:stun1.l.google.com:19302" },
];

const VIEWER_PING_MS = 3000;
const HEALTH_CHECK_MS = 4000;
const STUCK_CYCLES_BEFORE_RECONNECT = 2;

type SignalPayload =
  | { type: "offer"; sdp: string }
  | { type: "answer"; sdp: string }
  | { type: "ice"; candidate: RTCIceCandidateInit }
  | { type: "viewer-ready" }
  | { type: "save-recording"; title?: string };

function preferCameraConstraints(): MediaStreamConstraints {
  const isMobile = /iPhone|iPad|Android/i.test(navigator.userAgent);
  return {
    video: isMobile ? { facingMode: { ideal: "environment" } } : true,
    audio: true,
  };
}

function hasLiveVideo(stream: MediaStream | null) {
  return Boolean(stream?.getVideoTracks().some((t) => t.readyState === "live"));
}

export function useDeviceStream(deviceId: string | null, role: "broadcaster" | "viewer") {
  const videoRef = useRef<HTMLVideoElement>(null);
  const remoteStreamRef = useRef<MediaStream | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const sessionRef = useRef(0);
  const [connectKey, setConnectKey] = useState(0);
  const [viewerWatching, setViewerWatching] = useState(false);
  const [hasMedia, setHasMedia] = useState(false);
  const [waiting, setWaiting] = useState(role === "viewer");
  const [error, setError] = useState<string | null>(null);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);

  const reconnect = useCallback(() => {
    setConnectKey((k) => k + 1);
  }, []);

  const signalHandlerRef = useRef<{ onSaveRequest?: (title?: string) => void } | null>(null);
  const sendSignalRef = useRef<((payload: SignalPayload) => void) | null>(null);

  const requestSaveRecording = useCallback((title?: string) => {
    sendSignalRef.current?.({ type: "save-recording", title });
  }, []);

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

    const session = ++sessionRef.current;
    const isActive = () => sessionRef.current === session;

    setHasMedia(false);
    setViewerWatching(false);
    setWaiting(role === "viewer");
    setError(null);
    remoteStreamRef.current = null;

    let viewerReadyTimer: ReturnType<typeof setInterval> | null = null;
    let healthTimer: ReturnType<typeof setInterval> | null = null;
    let stuckCycles = 0;
    let lastOfferSentAt = 0;
    const pendingIce: RTCIceCandidateInit[] = [];
    const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });

    const requestFullReconnect = () => {
      if (!isActive()) return;
      setConnectKey((k) => k + 1);
    };

    const drainIce = async () => {
      if (!pc.remoteDescription) return;
      while (pendingIce.length > 0) {
        const candidate = pendingIce.shift()!;
        try {
          await pc.addIceCandidate(new RTCIceCandidate(candidate));
        } catch {
          // ignore stale candidates
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

    const startViewerReadyPing = () => {
      if (!isActive()) return;
      sendSignal({ type: "viewer-ready" });
      if (viewerReadyTimer) return;
      viewerReadyTimer = setInterval(() => sendSignal({ type: "viewer-ready" }), VIEWER_PING_MS);
    };

    const markBroadcasterViewerJoined = () => {
      if (!isActive()) return;
      setViewerWatching(true);
      setWaiting(false);
      setError(null);
    };

    const markViewerStreamReady = (stream: MediaStream) => {
      if (!isActive()) return;
      remoteStreamRef.current = stream;
      attachToVideo(stream);
      setHasMedia(true);
      setViewerWatching(true);
      setWaiting(false);
      setError(null);
      stuckCycles = 0;
      stopViewerReadyPing();
    };

    const channel = supabase.channel(`device-stream:${deviceId}`, {
      config: { broadcast: { ack: false } },
    });

    const sendSignal = (payload: SignalPayload) => {
      if (!isActive()) return;
      void channel.send({ type: "broadcast", event: "signal", payload });
    };
    sendSignalRef.current = sendSignal;

    pc.onicecandidate = (event) => {
      if (event.candidate) {
        sendSignal({ type: "ice", candidate: event.candidate.toJSON() });
      }
    };

    pc.ontrack = (event) => {
      if (role !== "viewer") return;
      const stream = event.streams[0] ?? (event.track ? new MediaStream([event.track]) : null);
      if (!stream) return;
      markViewerStreamReady(stream);
    };

    pc.onconnectionstatechange = () => {
      if (!isActive()) return;
      const state = pc.connectionState;
      if (state === "failed" || state === "disconnected") {
        if (role === "viewer") {
          setHasMedia(false);
          remoteStreamRef.current = null;
          setViewerWatching(false);
          setWaiting(true);
          pendingIce.length = 0;
          startViewerReadyPing();
        } else {
          setViewerWatching(false);
        }
      }
    };

    const applyOffer = async (sdp: string) => {
      if (!isActive() || hasLiveVideo(remoteStreamRef.current)) return;

      try {
        pendingIce.length = 0;
        await pc.setRemoteDescription({ type: "offer", sdp });
        await drainIce();
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        sendSignal({ type: "answer", sdp: answer.sdp ?? "" });
      } catch {
        startViewerReadyPing();
      }
    };

    const applyAnswer = async (sdp: string) => {
      if (!isActive() || pc.signalingState !== "have-local-offer") return;
      try {
        await pc.setRemoteDescription({ type: "answer", sdp });
        await drainIce();
        markBroadcasterViewerJoined();
      } catch {
        startViewerReadyPing();
      }
    };

    const sendOffer = async (iceRestart = false) => {
      if (!isActive() || !hasLiveVideo(localStreamRef.current)) return;
      try {
        pendingIce.length = 0;
        const offer = await pc.createOffer(iceRestart ? { iceRestart: true } : undefined);
        await pc.setLocalDescription(offer);
        lastOfferSentAt = Date.now();
        sendSignal({ type: "offer", sdp: offer.sdp ?? "" });
      } catch {
        // camera may still be starting
      }
    };

    const nudgeSignaling = () => {
      if (!isActive()) return;
      if (role === "viewer") {
        if (!hasLiveVideo(remoteStreamRef.current)) {
          startViewerReadyPing();
        }
        return;
      }
      if (hasLiveVideo(localStreamRef.current)) {
        void sendOffer(pc.signalingState === "stable");
      }
    };

    channel.on("broadcast", { event: "signal" }, ({ payload }) => {
      if (!isActive()) return;
      const msg = payload as SignalPayload;

      if (msg.type === "viewer-ready" && role === "broadcaster") {
        if (!hasLiveVideo(localStreamRef.current)) return;

        const now = Date.now();
        if (pc.signalingState === "have-local-offer" && pc.localDescription?.sdp) {
          sendSignal({ type: "offer", sdp: pc.localDescription.sdp });
          return;
        }

        if (now - lastOfferSentAt < 5000) return;
        void sendOffer(pc.signalingState === "stable");
        return;
      }

      if (msg.type === "offer" && role === "viewer") {
        void applyOffer(msg.sdp);
        return;
      }

      if (msg.type === "answer" && role === "broadcaster") {
        void applyAnswer(msg.sdp);
        return;
      }

      if (msg.type === "ice" && msg.candidate) {
        queueIce(msg.candidate);
      }
      // custom save-recording signal
      if (msg.type === "save-recording" && role === "broadcaster") {
        signalHandlerRef.current?.onSaveRequest?.(msg.title);
      }
    });

    const startBroadcaster = async () => {
      try {
        const mediaStream = await navigator.mediaDevices.getUserMedia(preferCameraConstraints());
        if (!isActive()) {
          mediaStream.getTracks().forEach((t) => t.stop());
          return;
        }

        localStreamRef.current = mediaStream;
        setLocalStream(mediaStream);
        setHasMedia(true);
        attachToVideo(mediaStream);

        mediaStream.getTracks().forEach((track) => pc.addTrack(track, mediaStream));
        await sendOffer(false);
        setWaiting(false);
      } catch (err) {
        if (!isActive()) return;
        setError(
          err instanceof Error && err.name === "NotAllowedError"
            ? "Camera permission is required to stream."
            : "Could not access camera.",
        );
      }
    };

    const onVisible = () => {
      if (document.visibilityState !== "visible" || !isActive()) return;
      nudgeSignaling();
    };

    healthTimer = setInterval(() => {
      if (!isActive()) return;

      const videoOk =
        role === "viewer"
          ? hasLiveVideo(remoteStreamRef.current)
          : hasLiveVideo(localStreamRef.current);

      if (videoOk) {
        stuckCycles = 0;
        return;
      }

      stuckCycles += 1;
      nudgeSignaling();

      if (stuckCycles >= STUCK_CYCLES_BEFORE_RECONNECT) {
        stuckCycles = 0;
        requestFullReconnect();
      }
    }, HEALTH_CHECK_MS);

    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", nudgeSignaling);

    void channel.subscribe((status) => {
      if (!isActive()) return;

      if (status === "SUBSCRIBED") {
        if (role === "viewer") {
          startViewerReadyPing();
        } else {
          void startBroadcaster();
        }
        return;
      }

      if (status === "CHANNEL_ERROR" || status === "TIMED_OUT" || status === "CLOSED") {
        requestFullReconnect();
      }
    });

    return () => {
      sessionRef.current += 1;
      stopViewerReadyPing();
      if (healthTimer) clearInterval(healthTimer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", nudgeSignaling);
      localStreamRef.current?.getTracks().forEach((t) => t.stop());
      localStreamRef.current = null;
      remoteStreamRef.current = null;
      pc.close();
      void supabase.removeChannel(channel);
    };
  }, [deviceId, role, attachToVideo, connectKey]);

  return {
    videoRef: setVideoRef,
    connected: viewerWatching,
    viewerWatching,
    hasMedia,
    waiting,
    error,
    localStream,
    reconnect,
      requestSaveRecording,
      setSignalHandler: (h: { onSaveRequest?: (title?: string) => void }) => {
        signalHandlerRef.current = h;
      },
  };
}
