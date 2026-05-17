"""Analyze one live camera feed end-to-end."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from backend.live.clip_condenser import (
    find_suspicious_segments,
    frames_to_jpeg_b64,
    select_condensed_frames,
    write_condensed_clip,
    write_preview_montage,
)
from backend.live.frame_source import check_live_feed, fetch_live_frames
from backend.live.nemotron_bridge import NemotronBridge
from backend.live.supabase_store import SupabaseStore
from backend.live.suspicious_detector import LiveSuspicionAnalyzer
from backend.storage import db
from backend.config import CONFIG
from backend.utils.logger import get_logger
from pipeline.event_buffer.rolling_buffer import BufferFrame

logger = get_logger("camera_worker")

COOLDOWN_SEC = 45.0


class CameraWorker:
    def __init__(self, device: dict, store: SupabaseStore | None = None):
        self.device = device
        self.device_id = device["id"]
        self.bubble_id = device["bubble"]
        self.name = device.get("name", "Camera")
        self.store = store or SupabaseStore()
        self.analyzer = LiveSuspicionAnalyzer(
            weights=os.getenv("YOLO_MODEL", "yolov8n.pt"),
        )
        self.nemotron = NemotronBridge()
        self._last_incident_at = 0.0
        self.clips_dir = Path(CONFIG.get("storage", {}).get("clips_dir", "./storage/clips")) / "live"
        self.clips_dir.mkdir(parents=True, exist_ok=True)

    def process_once(self) -> dict | None:
        supabase_url = os.getenv("SUPABASE_URL", "")
        status = check_live_feed(supabase_url, self.device_id, self.device.get("status", "offline"))
        if not status.is_live:
            return {"device_id": self.device_id, "live": False, "reason": status.reason}

        raw_frames = fetch_live_frames(supabase_url, self.device_id, status, max_frames=36, sample_fps=5.0)
        if not raw_frames:
            logger.info(
                "%s: no decodable frames (feed=%s url=%s) — is /device/live uploading live.webm?",
                self.name,
                status.reason,
                status.url,
            )
            return {
                "device_id": self.device_id,
                "live": True,
                "analyzed": False,
                "reason": "no_frames",
                "feed": status.reason,
            }

        buffer_frames: list[BufferFrame] = []
        peak_suspicion = 0.0
        peak_meta: dict = {}
        frame_num = 0

        for video_ts, frame in raw_frames:
            suspicion, meta = self.analyzer.analyze_frame(frame, frame_num, video_ts)
            if suspicion >= peak_suspicion:
                peak_suspicion = suspicion
                peak_meta = meta
            buffer_frames.append(
                BufferFrame(
                    frame=frame,
                    frame_num=frame_num,
                    timestamp=time.time(),
                    video_ts=video_ts,
                    suspicion=suspicion,
                )
            )
            frame_num += 1

        if not self.analyzer.should_escalate(peak_suspicion):
            return {
                "device_id": self.device_id,
                "live": True,
                "analyzed": True,
                "suspicious": False,
                "feed": status.reason,
                "peak_suspicion": round(peak_suspicion, 3),
                "yolo": peak_meta,
                "frames": len(raw_frames),
            }

        if time.time() - self._last_incident_at < COOLDOWN_SEC:
            return {
                "device_id": self.device_id,
                "live": True,
                "analyzed": True,
                "suspicious": True,
                "skipped": "cooldown",
                "feed": status.reason,
            }

        segments = find_suspicious_segments(buffer_frames)
        condensed = select_condensed_frames(buffer_frames, segments)
        incident_id = uuid.uuid4().hex[:12]
        clip_local = str(self.clips_dir / f"{self.device_id}_{incident_id}.mp4")
        preview_local = str(self.clips_dir / f"{self.device_id}_{incident_id}_preview.jpg")
        write_condensed_clip(condensed or buffer_frames, clip_local, fps=8.0)
        write_preview_montage(condensed or buffer_frames, preview_local)

        report = self.nemotron.analyze_sync(
            device_id=self.device_id,
            suspicion_score=peak_suspicion,
            window=condensed or buffer_frames,
            yolo_meta=peak_meta,
        )

        storage_path = f"{self.device_id}/activities/{incident_id}.mp4"
        preview_storage_path = f"{self.device_id}/activities/{incident_id}_preview.jpg"
        public_url = None
        preview_url = None
        recording_id = None
        if os.path.isfile(clip_local):
            public_url = self.store.upload_clip(storage_path, clip_local)
            recording_id = self.store.insert_recording(
                self.device_id,
                storage_path,
                duration_ms=int(max(1, len(condensed or buffer_frames)) * 125),
            )
        if os.path.isfile(preview_local):
            preview_url = self.store.upload_clip(
                preview_storage_path,
                preview_local,
                content_type="image/jpeg",
            )

        nemotron_meta = {
            "incident_confirmed": report.incident_confirmed,
            "confidence": report.confidence,
            "person_behavior": report.person_behavior,
            "recommended_action": report.recommended_action,
            "notifications": report.notifications,
            "yolo": peak_meta,
            "title": report.notifications.get("short", "Suspicious activity"),
            "summary": report.summary,
            "suspicion_score": peak_suspicion,
            "clip_storage_path": storage_path,
            "clip_url": public_url,
            "preview_storage_path": preview_storage_path if preview_url else None,
            "preview_url": preview_url,
            "incident_id": incident_id,
            "source": "live_monitor",
        }

        activity: dict = {}
        try:
            activity = self.store.insert_device_event(
                {
                    "bubble": self.bubble_id,
                    "device": self.device_id,
                    "recording_id": recording_id,
                    "event_type": report.incident_type,
                    "event_subtype": "live_monitor",
                    "risk_level": report.risk_level,
                    "confidence": float(report.confidence or peak_suspicion),
                    "incident_confirmed": report.incident_confirmed,
                    "metadata": nemotron_meta,
                }
            )
        except RuntimeError as e:
            logger.error(
                "Suspicious activity detected for %s (score=%.2f) but not saved: %s",
                self.device_id,
                peak_suspicion,
                e,
            )
            raise

        db.init_db(CONFIG["storage"]["db_path"])
        db.insert_event(
            CONFIG["storage"]["db_path"],
            {
                "ts": time.time(),
                "label": "suspicious_live",
                "score": peak_suspicion,
                "bbox": None,
                "frame_path": None,
                "clip_path": clip_local,
                "meta": {
                    "device_id": self.device_id,
                    "activity_id": activity.get("id"),
                    "nemotron": report.summary,
                    "clip_url": public_url,
                    "feed": status.reason,
                },
            },
        )

        self._last_incident_at = time.time()
        logger.info(
            "Incident %s device=%s score=%.2f confirmed=%s",
            incident_id,
            self.device_id,
            peak_suspicion,
            report.incident_confirmed,
        )

        return {
            "device_id": self.device_id,
            "live": True,
            "analyzed": True,
            "suspicious": True,
            "feed": status.reason,
            "incident_id": incident_id,
            "activity_id": activity.get("id"),
            "peak_suspicion": peak_suspicion,
            "summary": report.summary,
            "clip_url": public_url,
        }
