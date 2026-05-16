"""YOLO-based per-frame suspicion scoring for live feeds."""

from __future__ import annotations

import os
import time

import cv2
import numpy as np

from pipeline.detection.yolo_detector import YOLODetector
from pipeline.tracking.person_tracker import PersonTracker

# COCO classes: person + common "reaching / object" cues
_INTERACTION_CLASSES = frozenset({0, 39, 41, 63, 64, 67, 73, 76})


class LiveSuspicionAnalyzer:
    """Live analyzer tuned for snapshot bursts (not full video)."""

    PERSON_CONF_MIN = 0.32
    ESCALATE_SCORE = float(os.getenv("LIVE_ESCALATE_SCORE", "0.42"))
    SPIKE_SCORE = float(os.getenv("LIVE_SPIKE_SCORE", "0.52"))
    STREAK_TO_ESCALATE = int(os.getenv("LIVE_STREAK_ESCALATE", "2"))

    def __init__(self, weights: str = "yolov8n.pt", conf: float = 0.30):
        self.detector = YOLODetector(weights=weights, conf=conf)
        self.tracker = PersonTracker()
        self._prev_gray: np.ndarray | None = None
        self._high_streak = 0

    def analyze_frame(
        self,
        frame: np.ndarray,
        frame_num: int,
        video_ts: float,
    ) -> tuple[float, dict]:
        detections = self.detector.detect(frame)
        tracks = self.tracker.update(detections, frame_num)

        persons = [d for d in detections if d.cls == 0 and d.conf >= self.PERSON_CONF_MIN]
        person_count = len(persons)
        active_tracks = [t for t in tracks if t.active]
        loitering = any(t.frames_seen >= 6 for t in active_tracks)

        interaction_hits = [
            d for d in detections if d.cls in _INTERACTION_CLASSES and d.conf >= 0.35
        ]

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        motion = 0.0
        if self._prev_gray is not None and self._prev_gray.shape == gray.shape:
            diff = cv2.absdiff(self._prev_gray, gray)
            motion = float(np.mean(diff)) / 255.0
        self._prev_gray = gray

        suspicion = 0.0
        if person_count >= 1:
            suspicion += 0.32
        if person_count >= 2:
            suspicion += 0.18
        if loitering:
            suspicion += 0.12
        if len(interaction_hits) >= 2:
            suspicion += 0.12
        suspicion += min(0.40, motion * 2.0)
        if motion >= 0.08:
            suspicion += 0.12

        max_conf = max((d.conf for d in persons), default=0.0)
        if max_conf >= 0.55:
            suspicion += 0.12
        if max_conf >= 0.75:
            suspicion += 0.10

        suspicion = min(suspicion, 1.0)

        if suspicion >= self.ESCALATE_SCORE:
            self._high_streak += 1
        else:
            self._high_streak = max(0, self._high_streak - 1)

        meta = {
            "person_count": person_count,
            "track_count": len(active_tracks),
            "loitering": loitering,
            "motion": round(motion, 4),
            "max_person_conf": round(max_conf, 3),
            "interaction_objects": len(interaction_hits),
            "high_streak": self._high_streak,
            "analyzed_at": time.time(),
        }
        return suspicion, meta

    def should_escalate(self, suspicion: float) -> bool:
        if suspicion >= self.SPIKE_SCORE:
            return True
        return self._high_streak >= self.STREAK_TO_ESCALATE
