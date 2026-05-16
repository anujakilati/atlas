from collections import deque
from dataclasses import dataclass, field
import numpy as np
from pipeline.detection.yolo_detector import Detection


@dataclass
class Track:
    id: int
    center: tuple[int, int]
    box: tuple[int, int, int, int]
    frames_seen: int = 1
    frames_missing: int = 0
    path: deque = field(default_factory=lambda: deque(maxlen=90))
    first_frame: int = 0
    last_frame: int = 0

    @property
    def active(self):
        return self.frames_missing == 0


class PersonTracker:
    """Lightweight centroid tracker — person class only."""

    def __init__(self, max_missing=25, match_dist=130):
        self.tracks: dict[int, Track] = {}
        self._next_id = 0
        self.max_missing = max_missing
        self.match_dist  = match_dist

    def update(self, detections: list[Detection], frame_num: int) -> list[Track]:
        persons = [d for d in detections if d.cls == 0]

        # Age all tracks
        for t in self.tracks.values():
            t.frames_missing += 1

        # Greedy nearest-centroid matching
        for det in persons:
            cx, cy = det.center
            best_id, best_dist = None, float("inf")
            for tid, track in self.tracks.items():
                if track.frames_missing > 1:
                    continue
                d = np.hypot(cx - track.center[0], cy - track.center[1])
                if d < self.match_dist and d < best_dist:
                    best_dist, best_id = d, tid
            if best_id is not None:
                t = self.tracks[best_id]
                t.center, t.box = det.center, det.box
                t.frames_missing = 0
                t.frames_seen += 1
                t.last_frame = frame_num
                t.path.append(det.center)
            else:
                tid = self._next_id
                self._next_id += 1
                self.tracks[tid] = Track(
                    id=tid, center=det.center, box=det.box,
                    first_frame=frame_num, last_frame=frame_num,
                )
                self.tracks[tid].path.append(det.center)

        # Prune lost tracks
        self.tracks = {
            k: v for k, v in self.tracks.items()
            if v.frames_missing <= self.max_missing
        }
        return list(self.tracks.values())
