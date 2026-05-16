from collections import deque
from dataclasses import dataclass
import numpy as np
import time


@dataclass
class BufferFrame:
    frame: np.ndarray
    frame_num: int
    timestamp: float       # wall time
    video_ts: float        # video timestamp in seconds
    suspicion: float


class RollingBuffer:
    """
    In-memory circular buffer of raw frames.
    Default: 15s at the configured FPS.
    Never writes to disk unless explicitly triggered.
    """

    def __init__(self, fps: float, seconds: float = 15.0):
        maxlen = int(fps * seconds)
        self._buf: deque[BufferFrame] = deque(maxlen=maxlen)
        self.fps     = fps
        self.seconds = seconds

    def push(self, frame: np.ndarray, frame_num: int,
             video_ts: float, suspicion: float = 0.0):
        self._buf.append(BufferFrame(
            frame=frame.copy(),
            frame_num=frame_num,
            timestamp=time.time(),
            video_ts=video_ts,
            suspicion=suspicion,
        ))

    def get_window(self, pre_sec: float = 10.0,
                   post_sec: float = 5.0,
                   anchor_video_ts: float | None = None) -> list[BufferFrame]:
        """
        Return frames in [anchor - pre_sec, anchor + post_sec].
        anchor defaults to the latest frame if not given.
        """
        anchor = anchor_video_ts if anchor_video_ts is not None else (
            self._buf[-1].video_ts if self._buf else 0.0
        )
        return [
            f for f in self._buf
            if anchor - pre_sec <= f.video_ts <= anchor + post_sec
        ]

    def latest(self) -> BufferFrame | None:
        return self._buf[-1] if self._buf else None

    def __len__(self):
        return len(self._buf)
