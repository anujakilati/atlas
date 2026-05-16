"""Fetch frames from Supabase live feeds (live.webm chunks; optional live.jpg)."""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass

import cv2
import numpy as np
import requests

from backend.utils.logger import get_logger

logger = get_logger("frame_source")

LIVE_STALE_SEC = 25.0
MIN_FEED_BYTES = 500


@dataclass
class LiveFeedStatus:
    is_live: bool
    url: str
    last_modified: float | None
    reason: str


def live_webm_url(supabase_url: str, device_id: str) -> str:
    base = supabase_url.rstrip("/")
    return f"{base}/storage/v1/object/public/camera-feeds/{device_id}/live.webm"


def live_snapshot_url(supabase_url: str, device_id: str) -> str:
    base = supabase_url.rstrip("/")
    return f"{base}/storage/v1/object/public/camera-feeds/{device_id}/live.jpg"


def _head_info(url: str) -> tuple[bool, float | None, int | None]:
    try:
        r = requests.head(url, timeout=8, allow_redirects=True)
        if r.status_code != 200:
            return False, None, None
        lm = r.headers.get("Last-Modified")
        modified = None
        if lm:
            from email.utils import parsedate_to_datetime

            modified = parsedate_to_datetime(lm).timestamp()
        cl = r.headers.get("Content-Length")
        size = int(cl) if cl and cl.isdigit() else None
        return True, modified, size
    except Exception:
        return False, None, None


def _feed_valid(ok: bool, size: int | None, modified: float | None, *, require_fresh: bool) -> bool:
    if not ok or not size or size < MIN_FEED_BYTES:
        return False
    if not require_fresh:
        return True
    if not modified:
        return True
    return time.time() - modified <= LIVE_STALE_SEC


def check_live_feed(supabase_url: str, device_id: str, device_status: str) -> LiveFeedStatus:
    snap_url = live_snapshot_url(supabase_url, device_id)
    webm_url = live_webm_url(supabase_url, device_id)

    snap_ok, snap_mod, snap_len = _head_info(snap_url)
    webm_ok, webm_mod, webm_len = _head_info(webm_url)
    now = time.time()

    snap_fresh = _feed_valid(snap_ok, snap_len, snap_mod, require_fresh=True)
    webm_fresh = _feed_valid(webm_ok, webm_len, webm_mod, require_fresh=True)

    if snap_fresh:
        return LiveFeedStatus(True, snap_url, snap_mod, "snapshot")

    if webm_fresh:
        return LiveFeedStatus(True, webm_url, webm_mod, "webm")

    # Online in DB but storage empty/stale — do not treat tiny/corrupt files as live.
    if device_status == "online":
        if _feed_valid(webm_ok, webm_len, webm_mod, require_fresh=False):
            return LiveFeedStatus(True, webm_url, webm_mod, "webm_stale")
        if _feed_valid(snap_ok, snap_len, snap_mod, require_fresh=False):
            return LiveFeedStatus(True, snap_url, snap_mod, "snapshot_stale")

    if snap_ok and snap_len and snap_len < MIN_FEED_BYTES:
        return LiveFeedStatus(False, snap_url, snap_mod, "invalid_snapshot")

    if device_status != "online":
        return LiveFeedStatus(False, snap_url, None, f"device_status={device_status}")

    return LiveFeedStatus(False, webm_url or snap_url, None, "no_feed")


def download_live_chunk(url: str) -> str | None:
    try:
        r = requests.get(f"{url}?t={int(time.time() * 1000)}", timeout=20)
        r.raise_for_status()
        if len(r.content) < MIN_FEED_BYTES:
            logger.debug("live chunk too small (%s bytes)", len(r.content))
            return None
        fd, path = tempfile.mkstemp(suffix=".webm")
        os.close(fd)
        with open(path, "wb") as f:
            f.write(r.content)
        return path
    except Exception as e:
        logger.debug("download_live_chunk failed: %s", e)
        return None


def download_snapshot(url: str, *, cache_bust: bool = True) -> np.ndarray | None:
    try:
        fetch_url = url
        if cache_bust:
            fetch_url = f"{url}?t={int(time.time() * 1000)}"
        r = requests.get(fetch_url, timeout=15)
        r.raise_for_status()
        if len(r.content) < MIN_FEED_BYTES:
            return None
        arr = np.frombuffer(r.content, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame
    except Exception as e:
        logger.debug("download_snapshot failed: %s", e)
        return None


def fetch_snapshot_burst(
    snap_url: str,
    *,
    samples: int = 3,
    gap_sec: float = 1.5,
) -> list[tuple[float, np.ndarray]]:
    frames: list[tuple[float, np.ndarray]] = []
    for i in range(max(1, samples)):
        frame = download_snapshot(snap_url)
        if frame is not None:
            frames.append((i * gap_sec, frame))
        if i < samples - 1:
            time.sleep(gap_sec)
    return frames


def fetch_live_frames(
    supabase_url: str,
    device_id: str,
    feed: LiveFeedStatus,
    *,
    max_frames: int = 40,
    sample_fps: float = 5.0,
) -> list[tuple[float, np.ndarray]]:
    """Load frames for YOLO — snapshots if valid, else live.webm."""
    snap_url = live_snapshot_url(supabase_url, device_id)
    burst = int(os.getenv("LIVE_SNAPSHOT_SAMPLES", "3"))
    gap = float(os.getenv("LIVE_SNAPSHOT_GAP_SEC", "1.5"))

    if feed.reason.startswith("snapshot"):
        frames = fetch_snapshot_burst(snap_url, samples=burst, gap_sec=gap)
        if frames:
            return frames

    webm_url = feed.url if "webm" in feed.reason else live_webm_url(supabase_url, device_id)
    path = download_live_chunk(webm_url)
    if not path:
        return []

    try:
        frames = extract_frames(path, max_frames=max_frames, sample_fps=sample_fps)
        if not frames:
            logger.debug("webm decode returned no frames for %s", device_id)
        return frames
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def extract_frames(
    video_path: str,
    *,
    max_frames: int = 40,
    sample_fps: float = 5.0,
) -> list[tuple[float, np.ndarray]]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    step = max(1, int(round(src_fps / sample_fps)))
    frames: list[tuple[float, np.ndarray]] = []
    idx = 0
    frame_num = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            ts = frame_num / src_fps
            frames.append((ts, frame.copy()))
            if len(frames) >= max_frames:
                break
        idx += 1
        frame_num += 1

    cap.release()
    return frames
