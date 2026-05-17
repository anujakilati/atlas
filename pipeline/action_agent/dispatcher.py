"""
OpenClaw — Action Dispatcher
Maps an IncidentReport to an ActionSpec and queues it for NemoClaw execution.
Tier is determined purely by Nemotron's risk_level — not by incident type label.
Never blocks the real-time loop.
"""

import queue
import threading
from dataclasses import dataclass, field

from pipeline.nemotron_reasoning.engine import IncidentReport

# Actions are determined solely by risk_level Nemotron assigned from the footage.
TIER_ACTIONS: dict[str, list[str]] = {
    "low":      ["notify"],
    "medium":   ["notify", "lock_camera"],
    "high":     ["notify", "lock_camera", "smart_lock"],
    "critical": ["notify", "lock_camera", "smart_lock", "emergency_call"],
}


@dataclass
class ActionSpec:
    incident_id: str
    incident_type: str      # display label only — does not drive action routing
    risk_level: str         # drives tier selection
    person_behavior: str    # visual description from Nemotron — used in messages
    summary: str
    device_id: str | None
    bubble_id: str | None
    candidate_actions: list[str]
    metadata: dict = field(default_factory=dict)


class ActionDispatcher:
    def __init__(self) -> None:
        self._executor = None
        self._queue: queue.Queue = queue.Queue(maxsize=5)
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def set_executor(self, executor) -> None:
        self._executor = executor

    def dispatch_async(
        self,
        report: IncidentReport,
        device_id: str | None = None,
        bubble_id: str | None = None,
    ) -> None:
        if not report.incident_confirmed:
            return
        # False alarms are a no-op — Nemotron judged the footage as not a real incident.
        if report.incident_type == "false_alarm":
            return
        # Tier from risk_level; incident_type is passed through for display only
        candidate_actions = TIER_ACTIONS.get(report.risk_level, ["notify"])
        spec = ActionSpec(
            incident_id=report.incident_id,
            incident_type=report.incident_type,
            risk_level=report.risk_level,
            person_behavior=report.person_behavior,
            summary=report.summary,
            device_id=device_id,
            bubble_id=bubble_id,
            candidate_actions=candidate_actions,
            metadata={
                "objects_involved": report.objects_involved,
                "confidence": report.confidence,
                "recommended_action": report.recommended_action,
                "notifications": report.notifications,
            },
        )
        try:
            self._queue.put_nowait(spec)
        except queue.Full:
            print("[OpenClaw] queue full — dropping action spec")

    def _worker(self) -> None:
        while True:
            spec = self._queue.get()
            if spec is None:
                break
            if self._executor:
                try:
                    self._executor.execute(spec)
                except Exception as e:
                    print(f"[OpenClaw] executor error: {e}")
            self._queue.task_done()

    def stop(self) -> None:
        self._queue.put(None)
