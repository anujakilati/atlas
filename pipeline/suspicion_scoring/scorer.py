import time
from pipeline.roi_logic.zones import ProtectedZone
from pipeline.state_machine.incident_sm import State
from pipeline.tracking.person_tracker import Track


class SuspicionScorer:
    """
    Lightweight, heuristic-only suspicion scoring (0.0–1.0).
    Never calls any AI model — runs every frame.

    Score contributions:
      +0.20  person enters protected zone
      +0.25  prolonged dwell (scales up to this cap)
      +0.30  person exits zone after dwell (exit-with-item signal)
      +0.40  ROI pixel diff > threshold after person leaves  ← key for phone theft
      +0.25  hand-bbox overlap with zone while in interaction
    """

    ROI_CHANGE_THEFT    = 0.06   # fraction of ROI pixels changed → theft signal
    ROI_CHANGE_MINOR    = 0.03   # minor change (partial removal)
    DWELL_CAP_SEC       = 12.0
    MAX_SCORE           = 1.0

    def __init__(self):
        self._peak: float = 0.0
        self._exit_flagged: bool = False
        self._last_in_roi: bool = False
        self._dwell_start: float | None = None
        self._post_exit_score: float = 0.0

    def score(self, state: State, tracks: list[Track],
              zone: ProtectedZone, frame_num: int) -> float:

        in_roi  = bool(zone._tracks_in_roi)
        now     = time.monotonic()

        s = 0.0

        # ── ROI entry ──────────────────────────────────────────────────────
        if in_roi:
            s += 0.20

        # ── Dwell time ────────────────────────────────────────────────────
        if in_roi and self._dwell_start is None:
            self._dwell_start = now
        elif not in_roi:
            self._dwell_start = None

        if self._dwell_start is not None:
            dwell = now - self._dwell_start
            s += min(0.25, 0.25 * (dwell / self.DWELL_CAP_SEC))

        # ── Exit-after-dwell signal ───────────────────────────────────────
        just_exited = self._last_in_roi and not in_roi
        if just_exited and state.name in ("INTERACTION", "SUSPICIOUS_ACTIVITY"):
            self._exit_flagged = True
            s += 0.30

        if self._exit_flagged and not in_roi:
            s += 0.20   # sustain exit signal for a few frames

        # ── ROI pixel diff (object removal detection) ─────────────────────
        # Only meaningful after person has left and baseline exists
        if not in_roi and zone.has_baseline():
            # We need the current frame — caller must pre-compute and pass it
            # score is stored externally; check via zone.roi_change_score()
            pass   # applied in main loop where frame is available

        # Apply cached post-exit score (set from main loop)
        s += self._post_exit_score

        self._last_in_roi = in_roi
        self._peak = max(self._peak, s)
        return min(s, self.MAX_SCORE)

    def apply_roi_diff(self, change_frac: float):
        """Called from main loop after computing zone.roi_change_score()."""
        if change_frac >= self.ROI_CHANGE_THEFT:
            self._post_exit_score = 0.40
        elif change_frac >= self.ROI_CHANGE_MINOR:
            self._post_exit_score = 0.20
        else:
            self._post_exit_score = max(0.0, self._post_exit_score - 0.05)

    def reset(self):
        self._peak           = 0.0
        self._exit_flagged   = False
        self._last_in_roi    = False
        self._dwell_start    = None
        self._post_exit_score = 0.0
