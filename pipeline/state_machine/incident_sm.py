from dataclasses import dataclass, field
from enum import Enum, auto
import time


class State(Enum):
    IDLE                = auto()
    APPROACH            = auto()
    INTERACTION         = auto()
    SUSPICIOUS_ACTIVITY = auto()
    ESCALATED           = auto()
    INCIDENT_CONFIRMED  = auto()
    RESOLVED            = auto()


@dataclass
class Transition:
    from_state: State
    to_state: State
    timestamp: float
    frame_num: int
    tracker_ids: list[int]
    suspicion: float
    roi: str
    evidence_frame_idx: int | None = None


class IncidentStateMachine:
    ESCALATE_THRESHOLD  = 0.65
    RESOLVE_TIMEOUT_SEC = 8.0    # seconds of IDLE after escalation → RESOLVED

    def __init__(self, roi_label: str = "protected_zone"):
        self.state       = State.IDLE
        self.transitions: list[Transition] = []
        self.roi_label   = roi_label
        self._interaction_start: float | None = None
        self._last_person_ts: float = 0.0
        self._escalated_at: float | None = None

    @property
    def dwell_seconds(self) -> float:
        if self._interaction_start is None:
            return 0.0
        return time.monotonic() - self._interaction_start

    def _transition(self, new_state: State, frame_num: int,
                    tracker_ids: list[int], suspicion: float,
                    evidence_frame_idx: int | None = None):
        if new_state == self.state:
            return
        self.transitions.append(Transition(
            from_state=self.state,
            to_state=new_state,
            timestamp=time.time(),
            frame_num=frame_num,
            tracker_ids=tracker_ids,
            suspicion=suspicion,
            roi=self.roi_label,
            evidence_frame_idx=evidence_frame_idx,
        ))
        self.state = new_state

    def update(self, frame_num: int, tracker_ids_in_roi: list[int],
               tracker_ids_approaching: list[int],
               suspicion: float, now: float) -> State:
        has_roi      = bool(tracker_ids_in_roi)
        has_approach = bool(tracker_ids_approaching)
        all_ids      = tracker_ids_in_roi or tracker_ids_approaching

        if has_roi or has_approach:
            self._last_person_ts = now

        if self.state == State.IDLE:
            if has_approach:
                self._transition(State.APPROACH, frame_num, all_ids, suspicion)
            if has_roi:
                self._interaction_start = now
                self._transition(State.INTERACTION, frame_num, all_ids, suspicion)

        elif self.state == State.APPROACH:
            if has_roi:
                self._interaction_start = now
                self._transition(State.INTERACTION, frame_num, tracker_ids_in_roi, suspicion)
            elif not has_approach:
                self._transition(State.IDLE, frame_num, [], suspicion)

        elif self.state == State.INTERACTION:
            if suspicion >= self.ESCALATE_THRESHOLD:
                self._transition(State.SUSPICIOUS_ACTIVITY, frame_num,
                                 tracker_ids_in_roi, suspicion, frame_num)
            elif not has_roi and not has_approach:
                # Person left — check if we should flag
                if suspicion >= 0.3:
                    self._transition(State.SUSPICIOUS_ACTIVITY, frame_num,
                                     [], suspicion, frame_num)
                else:
                    self._transition(State.IDLE, frame_num, [], suspicion)
                self._interaction_start = None

        elif self.state == State.SUSPICIOUS_ACTIVITY:
            self._transition(State.ESCALATED, frame_num, all_ids, suspicion)
            self._escalated_at = now

        elif self.state == State.ESCALATED:
            pass   # Nemotron decides next state externally

        elif self.state == State.INCIDENT_CONFIRMED:
            if (not has_roi and not has_approach and
                    now - self._last_person_ts > self.RESOLVE_TIMEOUT_SEC):
                self._transition(State.RESOLVED, frame_num, [], suspicion)

        elif self.state == State.RESOLVED:
            # Fresh start after resolution
            if has_approach:
                self._transition(State.APPROACH, frame_num, all_ids, suspicion)

        return self.state

    def confirm_incident(self, frame_num: int):
        self._transition(State.INCIDENT_CONFIRMED, frame_num, [], 1.0)

    def reject_incident(self, frame_num: int):
        self._transition(State.RESOLVED, frame_num, [], 0.0)

    def transition_log(self) -> list[dict]:
        return [
            {
                "from": t.from_state.name,
                "to": t.to_state.name,
                "timestamp": t.timestamp,
                "frame": t.frame_num,
                "tracker_ids": t.tracker_ids,
                "suspicion": round(t.suspicion, 3),
                "roi": t.roi,
            }
            for t in self.transitions
        ]
