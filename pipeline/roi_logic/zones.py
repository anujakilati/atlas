import cv2
import numpy as np
from pipeline.tracking.person_tracker import Track


class ProtectedZone:
    """
    Monitors a rectangular ROI.
    Key capability: captures a baseline frame when the zone is clear,
    then diffs the ROI after a person exits to detect object removal.
    """

    def __init__(self, x1: int, y1: int, x2: int, y2: int,
                 approach_margin: int = 180):
        self.x1 = x1; self.y1 = y1
        self.x2 = x2; self.y2 = y2
        self.approach_margin = approach_margin

        self._baseline: np.ndarray | None = None   # clean ROI (no person)
        self._baseline_age: int = 0                # frames since baseline captured
        self._tracks_in_roi: set[int] = set()
        self._tracks_approaching: set[int] = set()

    # ── geometry ──────────────────────────────────────────────────────────────

    def contains(self, cx: int, cy: int) -> bool:
        return self.x1 <= cx <= self.x2 and self.y1 <= cy <= self.y2

    def approaches(self, cx: int, cy: int) -> bool:
        m = self.approach_margin
        return (self.x1-m <= cx <= self.x2+m and
                self.y1-m <= cy <= self.y2+m and
                not self.contains(cx, cy))

    def clip(self, frame: np.ndarray) -> np.ndarray:
        return frame[self.y1:self.y2, self.x1:self.x2]

    # ── baseline ──────────────────────────────────────────────────────────────

    def try_capture_baseline(self, frame: np.ndarray,
                             tracks_in_roi: set[int]) -> bool:
        """Capture a clean baseline when the zone has been empty for 30+ frames."""
        if tracks_in_roi:
            self._baseline_age = 0
            return False
        self._baseline_age += 1
        if self._baseline_age >= 30:
            self._baseline = self.clip(frame).copy()
            return True
        return False

    def roi_change_score(self, frame: np.ndarray) -> float:
        """
        Pixel-diff between current ROI and clean baseline.
        Returns 0.0-1.0 (fraction of pixels that changed significantly).
        Returns 0.0 if no baseline captured yet.
        """
        if self._baseline is None:
            return 0.0
        current = self.clip(frame)
        if current.shape != self._baseline.shape:
            return 0.0
        diff  = cv2.absdiff(current, self._baseline)
        gray  = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        _, th = cv2.threshold(gray, 35, 255, cv2.THRESH_BINARY)
        return float(np.sum(th > 0)) / th.size

    def has_baseline(self) -> bool:
        return self._baseline is not None

    # ── update ────────────────────────────────────────────────────────────────

    def update(self, tracks: list[Track], frame: np.ndarray):
        """
        Returns (entered_ids, exited_ids, currently_in_ids, approaching_ids).
        Also updates baseline when zone is clear.
        """
        now_in  = {t.id for t in tracks if self.contains(*t.center)}
        now_app = {t.id for t in tracks if self.approaches(*t.center)}

        entered = now_in  - self._tracks_in_roi
        exited  = self._tracks_in_roi - now_in

        self._tracks_in_roi       = now_in
        self._tracks_approaching  = now_app

        self.try_capture_baseline(frame, now_in)
        return entered, exited, now_in, now_app
