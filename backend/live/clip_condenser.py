"""Trim frame sequences to suspicious windows with minimal padding."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from pipeline.event_buffer.rolling_buffer import BufferFrame


@dataclass
class TimeSegment:
    start_ts: float
    end_ts: float


def find_suspicious_segments(
    frames: list[BufferFrame],
    *,
    threshold: float = 0.35,
    pad_sec: float = 0.75,
    merge_gap_sec: float = 1.0,
) -> list[TimeSegment]:
    """Merge high-suspicion frames into padded time ranges."""
    if not frames:
        return []

    raw: list[TimeSegment] = []
    start: float | None = None
    end: float | None = None

    for bf in frames:
        if bf.suspicion >= threshold:
            if start is None:
                start = bf.video_ts
            end = bf.video_ts
        elif start is not None and end is not None:
            raw.append(TimeSegment(start, end))
            start = None
            end = None

    if start is not None and end is not None:
        raw.append(TimeSegment(start, end))

    if not raw:
        return []

    merged: list[TimeSegment] = [raw[0]]
    for seg in raw[1:]:
        prev = merged[-1]
        if seg.start_ts - prev.end_ts <= merge_gap_sec:
            merged[-1] = TimeSegment(prev.start_ts, seg.end_ts)
        else:
            merged.append(seg)

    min_ts = frames[0].video_ts
    max_ts = frames[-1].video_ts
    padded: list[TimeSegment] = []
    for seg in merged:
        padded.append(
            TimeSegment(
                max(min_ts, seg.start_ts - pad_sec),
                min(max_ts, seg.end_ts + pad_sec),
            )
        )
    return padded


def select_condensed_frames(
    frames: list[BufferFrame],
    segments: list[TimeSegment],
) -> list[BufferFrame]:
    if not segments:
        return [bf for bf in frames if bf.suspicion >= 0.35] or frames[-6:]
    out: list[BufferFrame] = []
    for bf in frames:
        if any(seg.start_ts <= bf.video_ts <= seg.end_ts for seg in segments):
            out.append(bf)
    return out


def write_condensed_clip(
    frames: list[BufferFrame],
    output_path: str,
    fps: float = 8.0,
) -> str | None:
    if not frames:
        return None
    from backend.utils.video_encode import write_frames_mp4

    return write_frames_mp4([bf.frame for bf in frames], output_path, fps=fps)


def write_preview_montage(
    frames: list[BufferFrame],
    output_path: str,
) -> str | None:
    if not frames:
        return None
    from backend.utils.video_encode import write_preview_montage as _write_montage

    return _write_montage([bf.frame for bf in frames], output_path)


def frames_to_jpeg_b64(frames: list[BufferFrame], max_frames: int = 6) -> list[str]:
    import base64

    if not frames:
        return []
    step = max(1, len(frames) // max_frames)
    picked = frames[::step][:max_frames]
    out: list[str] = []
    for bf in picked:
        _, buf = cv2.imencode(".jpg", bf.frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
        out.append(base64.b64encode(buf).decode())
    return out
