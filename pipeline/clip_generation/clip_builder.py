import base64
import cv2
import numpy as np
from pathlib import Path
from pipeline.event_buffer.rolling_buffer import BufferFrame
from pipeline.state_machine.incident_sm import Transition


class ClipBuilder:
    """
    Selects 4–8 keyframes from an evidence window and writes
    an evidence clip + keyframe montage. Does NOT do any AI inference.
    """

    def __init__(self, output_dir: Path, fps: float):
        self.output_dir = output_dir
        self.fps        = fps
        output_dir.mkdir(parents=True, exist_ok=True)

    # ── Frame selection ────────────────────────────────────────────────────

    def select_keyframes(self, window: list[BufferFrame],
                         transitions: list[Transition],
                         target: int = 6) -> list[BufferFrame]:
        if not window:
            return []

        scored: list[tuple[float, BufferFrame]] = []
        transition_frames = {t.frame_num for t in transitions}

        for bf in window:
            s = bf.suspicion * 2.0                          # high suspicion → important
            if bf.frame_num in transition_frames:
                s += 3.0                                    # state-transition frame
            scored.append((s, bf))

        scored.sort(key=lambda x: -x[0])
        candidates = [bf for _, bf in scored[:target * 2]]

        # Spread them across the timeline (avoid clustering)
        if len(candidates) <= target:
            return sorted(candidates, key=lambda b: b.frame_num)

        candidates.sort(key=lambda b: b.frame_num)
        step = max(1, len(candidates) // target)
        selected = candidates[::step][:target]
        return sorted(selected, key=lambda b: b.frame_num)

    # ── Clip writing ───────────────────────────────────────────────────────

    def build_evidence_clip(self, window: list[BufferFrame],
                            incident_id: str) -> Path:
        if not window:
            return None
        path = self.output_dir / f"clip_{incident_id}.mp4"
        h, w = window[0].frame.shape[:2]
        writer = cv2.VideoWriter(
            str(path), cv2.VideoWriter_fourcc(*"mp4v"),
            self.fps, (w, h))
        for bf in window:
            writer.write(bf.frame)
        writer.release()
        return path

    def build_montage(self, keyframes: list[BufferFrame],
                      incident_id: str, cols: int = 3) -> Path:
        if not keyframes:
            return None
        h, w = keyframes[0].frame.shape[:2]
        th, tw = 270, 480   # thumbnail size
        rows = (len(keyframes) + cols - 1) // cols
        canvas = np.zeros((rows * th, cols * tw, 3), dtype=np.uint8)
        for i, bf in enumerate(keyframes):
            r, c = divmod(i, cols)
            thumb = cv2.resize(bf.frame, (tw, th))
            cv2.putText(thumb, f"t={bf.video_ts:.1f}s  s={bf.suspicion:.2f}",
                        (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,255,100), 1)
            canvas[r*th:(r+1)*th, c*tw:(c+1)*tw] = thumb
        path = self.output_dir / f"montage_{incident_id}.jpg"
        cv2.imwrite(str(path), canvas)
        return path

    # ── Payload encoding ───────────────────────────────────────────────────

    @staticmethod
    def frames_to_b64(keyframes: list[BufferFrame]) -> list[str]:
        b64s = []
        for bf in keyframes:
            _, buf = cv2.imencode(".jpg", bf.frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            b64s.append(base64.b64encode(buf).decode())
        return b64s
