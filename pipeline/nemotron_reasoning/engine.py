"""
Async Nemotron-VL reasoning engine.
Runs in a background thread — never blocks the realtime loop.
"""

import json
import os
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable

from openai import OpenAI


MODEL = "nvidia/nemotron-nano-12b-v2-vl"


@dataclass
class IncidentPayload:
    incident_id: str
    suspicion_score: float
    timeline: list[dict]
    state_transitions: list[dict]
    evidence_b64: list[str]          # base64 JPEGs
    roi_metadata: dict
    tracker_summary: dict
    clip_path: str | None = None


@dataclass
class IncidentReport:
    incident_id: str
    incident_confirmed: bool
    incident_type: str
    confidence: float
    objects_involved: list[str]
    person_behavior: str
    risk_level: str
    recommended_action: str
    summary: str
    notifications: dict              # short / medium / long
    analyzed_at: float
    evidence_frame_count: int


PROMPT_TEMPLATE = """\
You are a security AI analyzing a suspicious event captured by a surveillance system.

STRUCTURED CONTEXT:
{context_json}

You are given {n_frames} evidence frames from the incident window.
Analyze the frames and the context. Respond with ONLY valid JSON — no markdown, no extra text:

{{
  "incident_confirmed": true,
  "incident_type": "theft|loitering|suspicious_behavior|false_alarm",
  "confidence": 0.0,
  "objects_involved": [],
  "person_behavior": "brief description of what the person did",
  "risk_level": "low|medium|high|critical",
  "recommended_action": "monitor|alert_operator|call_security|lock_down",
  "summary": "one sentence operator-ready summary",
  "notifications": {{
    "short": "Suspicious object removal detected.",
    "medium": "Protected item removed from monitored zone at {ts}.",
    "long": "Detailed operator report here."
  }}
}}"""


class NemotronEngine:
    def __init__(self, max_queue: int = 3):
        self._client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=os.environ["NVIDIA_API_KEY"],
        )
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue)
        self._callbacks: dict[str, Callable] = {}
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def analyze_async(self, payload: IncidentPayload,
                      on_result: Callable[[IncidentReport], None]):
        """Non-blocking. Drops the request if queue is full."""
        try:
            self._callbacks[payload.incident_id] = on_result
            self._queue.put_nowait(payload)
            return True
        except queue.Full:
            return False

    def _worker(self):
        while True:
            payload = self._queue.get()
            if payload is None:
                break
            try:
                report = self._analyze(payload)
            except Exception as e:
                report = IncidentReport(
                    incident_id=payload.incident_id,
                    incident_confirmed=False,
                    incident_type="error",
                    confidence=0.0,
                    objects_involved=[],
                    person_behavior="",
                    risk_level="low",
                    recommended_action="monitor",
                    summary=f"Analysis failed: {e}",
                    notifications={"short": "Analysis error.", "medium": "", "long": ""},
                    analyzed_at=time.time(),
                    evidence_frame_count=len(payload.evidence_b64),
                )
            cb = self._callbacks.pop(payload.incident_id, None)
            if cb:
                cb(report)
            self._queue.task_done()

    def _analyze(self, payload: IncidentPayload) -> IncidentReport:
        ctx = {
            "incident_id": payload.incident_id,
            "suspicion_score": round(payload.suspicion_score, 3),
            "roi": payload.roi_metadata,
            "tracker": payload.tracker_summary,
            "state_transitions": payload.state_transitions,
            "timeline": payload.timeline,
        }
        ts = time.strftime("%H:%M:%S", time.localtime())
        prompt = PROMPT_TEMPLATE.format(
            context_json=json.dumps(ctx, indent=2),
            n_frames=len(payload.evidence_b64),
            ts=ts,
        )

        # Build multimodal message content
        content = []
        for b64 in payload.evidence_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })
        content.append({"type": "text", "text": prompt})

        resp = self._client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": content}],
            temperature=0.1,
            max_tokens=600,
        )
        raw = resp.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()

        data = json.loads(raw)
        return IncidentReport(
            incident_id=payload.incident_id,
            incident_confirmed=data.get("incident_confirmed", False),
            incident_type=data.get("incident_type", "unknown"),
            confidence=float(data.get("confidence", 0.0)),
            objects_involved=data.get("objects_involved", []),
            person_behavior=data.get("person_behavior", ""),
            risk_level=data.get("risk_level", "low"),
            recommended_action=data.get("recommended_action", "monitor"),
            summary=data.get("summary", ""),
            notifications=data.get("notifications", {}),
            analyzed_at=time.time(),
            evidence_frame_count=len(payload.evidence_b64),
        )

    def stop(self):
        self._queue.put(None)
