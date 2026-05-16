"""
Interaction Session — replaces single-event IncidentStateMachine.

A session lives from first approach until inactivity timeout.
Multiple object events accumulate within one session.
Nemotron is called:
  - After first confirmed removal (immediate partial report)
  - At session end with full context (comprehensive report)
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto


class SessionState(Enum):
    IDLE             = auto()
    APPROACH         = auto()
    ACTIVE           = auto()
    OBJECT_EVENT     = auto()
    EXIT_MONITORING  = auto()
    COMPLETE         = auto()


@dataclass
class ObjectEvent:
    obj_id: str
    label: str
    event_type: str         # "removed" | "returned" | "touched"
    frame_num: int
    video_ts: float
    confidence: float
    cell: tuple[int, int]


@dataclass
class StateTransition:
    from_state: SessionState
    to_state: SessionState
    timestamp: float
    frame_num: int
    reason: str


class InteractionSession:
    INACTIVITY_TIMEOUT_SEC = 10.0   # session ends after this much idle time
    ESCALATE_AFTER_REMOVALS = 1     # fire Nemotron after this many removals

    def __init__(self, start_frame: int, start_video_ts: float):
        self.session_id        = uuid.uuid4().hex[:8]
        self.state             = SessionState.APPROACH
        self.start_frame       = start_frame
        self.start_video_ts    = start_video_ts
        self.last_activity_ts  = time.monotonic()   # wall time
        self.subject_ids: set[int] = set()
        self.object_events: list[ObjectEvent] = []
        self.transitions: list[StateTransition] = []
        self.peak_suspicion    = 0.0
        self.nemotron_calls    = 0                  # how many times Nemotron was called
        self._last_escalate_count = 0               # object_events count at last call

    # ── State transitions ─────────────────────────────────────────────────────

    def _transition(self, new_state: SessionState, frame_num: int, reason: str):
        if new_state == self.state:
            return
        self.transitions.append(StateTransition(
            from_state=self.state, to_state=new_state,
            timestamp=time.time(), frame_num=frame_num, reason=reason,
        ))
        self.state = new_state

    # ── Per-frame update ──────────────────────────────────────────────────────

    def update(self, frame_num: int, in_roi_ids: set[int],
               approaching_ids: set[int], suspicion: float,
               now_mono: float):
        has_roi  = bool(in_roi_ids)
        has_appr = bool(approaching_ids)
        active   = has_roi or has_appr

        if active:
            self.last_activity_ts = now_mono
            self.subject_ids |= (in_roi_ids | approaching_ids)

        self.peak_suspicion = max(self.peak_suspicion, suspicion)

        if self.state == SessionState.APPROACH:
            if has_roi:
                self._transition(SessionState.ACTIVE, frame_num, "entered_roi")

        elif self.state == SessionState.ACTIVE:
            if not active:
                self._transition(SessionState.EXIT_MONITORING, frame_num, "person_left")

        elif self.state == SessionState.OBJECT_EVENT:
            if not active:
                self._transition(SessionState.EXIT_MONITORING, frame_num, "person_left")

        elif self.state == SessionState.EXIT_MONITORING:
            if has_roi:
                self._transition(SessionState.ACTIVE, frame_num, "re_entered")
            elif now_mono - self.last_activity_ts > self.INACTIVITY_TIMEOUT_SEC:
                self._transition(SessionState.COMPLETE, frame_num, "inactivity_timeout")

    # ── Object events ─────────────────────────────────────────────────────────

    def record_object_event(self, event: ObjectEvent):
        self.object_events.append(event)
        self.last_activity_ts = time.monotonic()
        if self.state in (SessionState.ACTIVE, SessionState.EXIT_MONITORING,
                          SessionState.APPROACH):
            self.state = SessionState.OBJECT_EVENT

    # ── Escalation checks ─────────────────────────────────────────────────────

    def should_escalate_partial(self) -> bool:
        """True when new removal events have arrived since last Nemotron call."""
        new_removals = sum(
            1 for e in self.object_events[self._last_escalate_count:]
            if e.event_type == "removed"
        )
        return new_removals >= self.ESCALATE_AFTER_REMOVALS

    def mark_escalated(self):
        self._last_escalate_count = len(self.object_events)
        self.nemotron_calls += 1

    def should_escalate_final(self) -> bool:
        """Fire final full-session report when session completes."""
        return (self.state == SessionState.COMPLETE
                and len(self.object_events) > self._last_escalate_count)

    @property
    def is_complete(self) -> bool:
        return self.state == SessionState.COMPLETE

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "state": self.state.name,
            "start_video_ts": round(self.start_video_ts, 2),
            "subject_ids": list(self.subject_ids),
            "peak_suspicion": round(self.peak_suspicion, 3),
            "object_events": [
                {
                    "obj_id": e.obj_id,
                    "label": e.label,
                    "event": e.event_type,
                    "frame": e.frame_num,
                    "ts": round(e.video_ts, 2),
                    "confidence": round(e.confidence, 3),
                }
                for e in self.object_events
            ],
            "transitions": [
                {
                    "from": t.from_state.name,
                    "to": t.to_state.name,
                    "frame": t.frame_num,
                    "reason": t.reason,
                }
                for t in self.transitions
            ],
        }
