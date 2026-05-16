try:
    from deep_sort_realtime.deepsort_tracker import DeepSort
except Exception:
    DeepSort = None


class DummyTracker:
    def __init__(self):
        self._next = 1

    def update_tracks(self, detections, frame=None):
        # mimic DeepSort track objects with minimal interface
        out = []
        for det in detections:
            class T:
                def __init__(self, tid, det):
                    self.track_id = tid
                    self._det = det

                def is_confirmed(self):
                    return True

                def to_ltrb(self):
                    # deep-sort uses ltrb (left, top, right, bottom)
                    return [self._det[0], self._det[1], self._det[2], self._det[3]]

            out.append(T(self._next, det))
            self._next += 1
        return out


class TrackerWrapper:
    def __init__(self, max_age: int = 30, n_init: int = 3):
        self._uses_deepsort = False
        if DeepSort is not None:
            try:
                self.tracker = DeepSort(max_age=max_age, n_init=n_init)
                self._uses_deepsort = True
            except Exception:
                # fallback to dummy tracker if DeepSort instantiation fails (missing heavy deps)
                self.tracker = DummyTracker()
                self._uses_deepsort = False
        else:
            self.tracker = DummyTracker()

    def update(self, detections, frame):
        # detections: list of [x1,y1,x2,y2,score,det_class]
        tracks = self.tracker.update_tracks(detections, frame=frame)
        out = []
        for t in tracks:
            if not t.is_confirmed():
                continue
            # det_class may be stored differently; try attribute then fallback
            det_class = getattr(t, 'det_class', None)
            # if using DummyTracker, input det_class is in the underlying det
            if det_class is None and hasattr(t, '_det'):
                det_class = t._det[5] if len(t._det) > 5 else None
            out.append({"track_id": t.track_id, "bbox": t.to_ltrb(), "det_class": det_class})
        return out
