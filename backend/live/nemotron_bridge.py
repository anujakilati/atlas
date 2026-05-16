"""Nemotron VL analysis with NVIDIA Integrate API or local Ollama fallback."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import requests

from backend.utils.logger import get_logger
from pipeline.clip_generation.clip_builder import ClipBuilder
from pipeline.event_buffer.rolling_buffer import BufferFrame
from pipeline.nemotron_reasoning.engine import IncidentPayload, IncidentReport, NemotronEngine

logger = get_logger("nemotron_bridge")


def _ollama_analyze(
    endpoint: str,
    evidence_b64: list[str],
    context: dict[str, Any],
) -> dict[str, Any]:
    prompt = (
        "You are a security AI. Analyze suspicious surveillance activity. "
        "Respond with ONLY JSON: incident_confirmed, incident_type, confidence, "
        "objects_involved, person_behavior, risk_level, recommended_action, summary, "
        "notifications {short, medium, long}.\n"
        f"Context: {json.dumps(context)}"
    )
    try:
        r = requests.post(
            f"{endpoint.rstrip('/')}/api/generate",
            json={"model": "llava", "prompt": prompt, "stream": False},
            timeout=60,
        )
        r.raise_for_status()
        raw = r.json().get("response", "{}")
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except Exception as e:
        logger.warning("Ollama Nemotron fallback failed: %s", e)
        return {
            "incident_confirmed": context.get("suspicion_score", 0) >= 0.6,
            "incident_type": "suspicious_behavior",
            "confidence": context.get("suspicion_score", 0.5),
            "objects_involved": [],
            "person_behavior": "Person detected in monitored area.",
            "risk_level": "medium" if context.get("suspicion_score", 0) >= 0.65 else "low",
            "recommended_action": "alert_operator",
            "summary": "Suspicious activity detected by YOLO.",
            "notifications": {
                "short": "Suspicious activity on camera.",
                "medium": "YOLO flagged suspicious behavior; review the clip.",
                "long": str(e),
            },
        }


class NemotronBridge:
    def __init__(self):
        self._engine: NemotronEngine | None = None
        if os.getenv("NVIDIA_API_KEY"):
            try:
                self._engine = NemotronEngine()
            except Exception as e:
                logger.warning("NemotronEngine unavailable: %s", e)
        self._ollama_url = os.getenv("NEMOTRON_URL", "http://localhost:11434")

    def analyze_sync(
        self,
        *,
        device_id: str,
        suspicion_score: float,
        window: list[BufferFrame],
        yolo_meta: dict[str, Any],
    ) -> IncidentReport:
        builder = ClipBuilder(Path("storage/clips/live"), fps=8.0)
        keyframes = builder.select_keyframes(window, [], target=6)
        if not keyframes:
            keyframes = window[:: max(1, len(window) // 4)][:6] or [window[-1]]
        b64s = ClipBuilder.frames_to_b64(keyframes)

        incident_id = f"{device_id}_{uuid.uuid4().hex[:8]}"
        ctx = {
            "device_id": device_id,
            "suspicion_score": round(suspicion_score, 3),
            "yolo": yolo_meta,
            "timeline": [
                {"ts": round(b.video_ts, 2), "suspicion": round(b.suspicion, 3)}
                for b in window[:: max(1, len(window) // 10)]
            ],
        }

        if self._engine and b64s:
            payload = IncidentPayload(
                incident_id=incident_id,
                suspicion_score=suspicion_score,
                timeline=ctx["timeline"],
                state_transitions=[],
                evidence_b64=b64s,
                roi_metadata={"source": "live_camera", "yolo": yolo_meta},
                tracker_summary={"person_count": yolo_meta.get("person_count", 0)},
            )
            result: IncidentReport | None = None

            def _cb(report: IncidentReport):
                nonlocal result
                result = report

            self._engine.analyze_async(payload, _cb)
            deadline = time.time() + 90
            while result is None and time.time() < deadline:
                time.sleep(0.2)
            if result is not None:
                return result

        data = _ollama_analyze(self._ollama_url, b64s, ctx)
        return IncidentReport(
            incident_id=incident_id,
            incident_confirmed=bool(data.get("incident_confirmed", suspicion_score >= 0.55)),
            incident_type=str(data.get("incident_type", "suspicious_behavior")),
            confidence=float(data.get("confidence", suspicion_score)),
            objects_involved=list(data.get("objects_involved", [])),
            person_behavior=str(data.get("person_behavior", "")),
            risk_level=str(data.get("risk_level", "medium")),
            recommended_action=str(data.get("recommended_action", "alert_operator")),
            summary=str(data.get("summary", "Suspicious activity detected.")),
            notifications=dict(data.get("notifications", {})),
            analyzed_at=time.time(),
            evidence_frame_count=len(b64s),
        )
