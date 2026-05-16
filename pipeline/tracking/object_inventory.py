"""
Object inventory: tracks what's on the table and detects removals.

Two-layer approach:
  1. Pixel-diff grid  — divides ROI into cells, each monitored independently.
                        Catches removals of ANY object regardless of YOLO class.
  2. YOLO label map   — overlaid at catalog time to give human-readable names.
"""

from dataclasses import dataclass, field
import cv2
import numpy as np
from pipeline.detection.yolo_detector import Detection
from pipeline.roi_logic.zones import ProtectedZone


@dataclass
class ProtectedObject:
    obj_id: str
    label: str                   # YOLO class name or "unknown_region"
    cell: tuple[int, int]        # (row, col) in the diff grid
    status: str = "PRESENT"      # PRESENT | TOUCHED | REMOVED | RETURNED
    first_seen_frame: int = 0
    last_seen_frame: int = 0
    removal_frames: int = 0      # consecutive frames the cell looks different
    confidence: float = 0.0
    removal_video_ts: float = 0.0


class ObjectInventory:
    """
    Grid-based ROI monitor.
    - GRID_ROWS × GRID_COLS cells covering the protected zone.
    - Baseline is captured once the zone is clear for MIN_CLEAR_FRAMES frames.
    - Each cell is checked every update; cells that diverge from baseline
      accumulate removal_frames and eventually flip to REMOVED.
    """

    GRID_ROWS        = 3
    GRID_COLS        = 4
    MIN_CLEAR_FRAMES = 10      # frames zone must be clear before cataloging
    REMOVAL_FRAMES   = 12      # consecutive diff frames → REMOVED
    DIFF_THRESHOLD   = 30      # per-pixel intensity change to count
    CHANGE_FRACTION  = 0.08    # fraction of cell pixels that must change

    def __init__(self):
        self.objects: dict[str, ProtectedObject] = {}
        self._baseline_cells: dict[tuple, np.ndarray] = {}
        self._ready = False
        self._clear_streak = 0
        self._yolo_label_map: dict[tuple, str] = {}   # cell → label

    # ── Baseline ──────────────────────────────────────────────────────────────

    def _cell_image(self, roi_img: np.ndarray, row: int, col: int) -> np.ndarray:
        h, w = roi_img.shape[:2]
        rh, cw = h // self.GRID_ROWS, w // self.GRID_COLS
        return roi_img[row*rh:(row+1)*rh, col*cw:(col+1)*cw]

    def try_catalog(self, frame: np.ndarray, zone: ProtectedZone,
                    detections: list[Detection], in_roi_ids: set,
                    frame_num: int) -> bool:
        """
        Try to establish baseline. Returns True when catalog is ready.
        Must be called every frame while session is not yet started.
        """
        if self._ready:
            return True

        if in_roi_ids:
            self._clear_streak = 0
            return False

        self._clear_streak += 1
        if self._clear_streak < self.MIN_CLEAR_FRAMES:
            return False

        # Snapshot each cell
        roi_img = zone.clip(frame)
        for r in range(self.GRID_ROWS):
            for c in range(self.GRID_COLS):
                cell_img = self._cell_image(roi_img, r, c)
                self._baseline_cells[(r, c)] = cv2.cvtColor(
                    cell_img, cv2.COLOR_BGR2GRAY).astype(np.float32)

        # Map YOLO detections to cells for labeling
        non_persons = [d for d in detections
                       if d.cls != 0 and zone.contains(*d.center)]
        for d in non_persons:
            # Convert detection center to cell coords
            rx, ry = d.center[0] - zone.x1, d.center[1] - zone.y1
            roi_w = zone.x2 - zone.x1
            roi_h = zone.y2 - zone.y1
            col = min(int(rx / roi_w * self.GRID_COLS), self.GRID_COLS - 1)
            row = min(int(ry / roi_h * self.GRID_ROWS), self.GRID_ROWS - 1)
            self._yolo_label_map[(row, col)] = d.label

        # Create ProtectedObject per cell that has content
        # (we track all cells, but only report changes in cells that had content)
        for r in range(self.GRID_ROWS):
            for c in range(self.GRID_COLS):
                obj_id = f"cell_{r}_{c}"
                label  = self._yolo_label_map.get((r, c), f"item@{r},{c}")
                self.objects[obj_id] = ProtectedObject(
                    obj_id=obj_id, label=label, cell=(r, c),
                    first_seen_frame=frame_num, last_seen_frame=frame_num,
                )

        self._ready = True
        return True

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, frame: np.ndarray, zone: ProtectedZone,
               frame_num: int, video_ts: float) -> list[ProtectedObject]:
        """
        Returns list of objects newly confirmed REMOVED this frame.
        Call only while session is active.
        """
        if not self._ready:
            return []

        roi_img  = zone.clip(frame)
        newly_removed: list[ProtectedObject] = []

        for obj_id, obj in self.objects.items():
            if obj.status == "REMOVED":
                continue

            r, c     = obj.cell
            baseline = self._baseline_cells.get((r, c))
            if baseline is None:
                continue

            cell_img = self._cell_image(roi_img, r, c)
            gray     = cv2.cvtColor(cell_img, cv2.COLOR_BGR2GRAY).astype(np.float32)

            diff  = np.abs(gray - baseline)
            frac  = float(np.mean(diff > self.DIFF_THRESHOLD))

            if frac >= self.CHANGE_FRACTION:
                obj.removal_frames += 1
                obj.confidence = obj.removal_frames / self.REMOVAL_FRAMES
                if obj.removal_frames >= self.REMOVAL_FRAMES:
                    obj.status             = "REMOVED"
                    obj.removal_video_ts   = video_ts
                    obj.last_seen_frame    = frame_num
                    newly_removed.append(obj)
            else:
                obj.removal_frames = max(0, obj.removal_frames - 1)
                obj.confidence     = obj.removal_frames / self.REMOVAL_FRAMES
                obj.last_seen_frame = frame_num

        return newly_removed

    def removed_count(self) -> int:
        return sum(1 for o in self.objects.values() if o.status == "REMOVED")

    def present_labels(self) -> list[str]:
        return [o.label for o in self.objects.values() if o.status == "PRESENT"
                and o.label != f"item@{o.cell[0]},{o.cell[1]}"]

    def removed_labels(self) -> list[str]:
        return [o.label for o in self.objects.values() if o.status == "REMOVED"]

    def reset(self):
        self.objects         = {}
        self._baseline_cells = {}
        self._ready          = False
        self._clear_streak   = 0
        self._yolo_label_map = {}

    @property
    def ready(self) -> bool:
        return self._ready
