"""Multi-camera YOLO MJPEG server for the 4 sus-cam simulation videos.

Streams four YOLO-annotated MJPEG feeds on a single HTTP server, plays each
video at ~2x source speed, and posts a `device_events` row (plus an optional
character profile) to Supabase when any cam's suspicion crosses threshold.

Run:
    python scripts/yolo_multi_watch.py
"""
from __future__ import annotations

import http.server
import json
import os
import sys
import threading
import time
from collections import deque
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Reuse the event-pipeline helpers from show_latest_event (env loading + db
# imports happen on its module load).
import requests as req

from scripts.show_latest_event import (
    _supabase_headers,
    analyze_suspect,
    compute_clarity_score,
    crop_person,
    find_person_detections,
    is_duplicate_character,
    upload_crop_to_storage,
    upload_replay_to_storage,
)

PORT = 8765
BUFFER_SECONDS = 5
ESCALATE_COOLDOWN_S = 30.0
ESCALATE_THRESHOLD = 0.60
PLAYBACK_SPEED = 3.0  # 3x source playback
FRAME_STRIDE = 4      # read every Nth source frame
INFER_EVERY = 3       # only run YOLO every Nth emitted frame; reuse boxes between
JPEG_QUALITY = 65

CAM_CONFIG = [
    {"id": 1, "label": "Sim Cam 1", "video": "videos/sus-cam-1.mp4", "placement": "Sim Cam 1"},
    {"id": 2, "label": "Sim Cam 2", "video": "videos/sus-cam-2.MOV", "placement": "Sim Cam 2"},
    {"id": 3, "label": "Sim Cam 3", "video": "videos/sus-cam-3.mp4", "placement": "Sim Cam 3"},
    {"id": 4, "label": "Sim Cam 4", "video": "videos/sus-cam-4.mp4", "placement": "Sim Cam 4"},
]

# Single shared YOLO instance lives inside scripts.show_latest_event; serialize
# access since ultralytics predict is not thread-safe.
_DETECTOR_LOCK = threading.Lock()


class _FrameStore:
    def __init__(self):
        self._data: bytes | None = None
        self._lock = threading.Lock()

    def put(self, data: bytes) -> None:
        with self._lock:
            self._data = data

    def get(self) -> bytes | None:
        with self._lock:
            return self._data


STORES: dict[int, _FrameStore] = {c["id"]: _FrameStore() for c in CAM_CONFIG}
ACTIVE = threading.Event()


# ── HTTP handler ──────────────────────────────────────────────────────────────


class _Handler(http.server.BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        path = self.path.split("?", 1)[0]

        if path.startswith("/stream/"):
            try:
                cam_id = int(path.rsplit("/", 1)[-1])
            except ValueError:
                self.send_error(400)
                return
            store = STORES.get(cam_id)
            if store is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self._cors()
            self.end_headers()
            try:
                while ACTIVE.is_set():
                    frame = store.get()
                    if frame is None:
                        time.sleep(0.05)
                        continue
                    try:
                        self.wfile.write(
                            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                        )
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    time.sleep(1 / 30)
            except Exception:
                pass

        elif path == "/status":
            body = json.dumps(
                {
                    "active": ACTIVE.is_set(),
                    "cams": [{"id": c["id"], "label": c["label"]} for c in CAM_CONFIG],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_error(404)

    def log_message(self, *_args) -> None:  # silence access logs
        pass


# ── Supabase bootstrap ────────────────────────────────────────────────────────


def resolve_bubble_id(sb_url: str, key: str) -> str | None:
    env_id = os.environ.get("BUBBLE_ID")
    if env_id:
        return env_id
    try:
        r = req.get(
            f"{sb_url}/rest/v1/bubbles?select=id&limit=1",
            headers=_supabase_headers(key),
            timeout=10,
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0]["id"] if rows else None
    except Exception as e:
        print(f"[Bootstrap] Could not fetch bubble id: {e}")
        return None


def ensure_sim_devices(sb_url: str, key: str, bubble_id: str) -> dict[int, str]:
    """Upsert one device row per cam under this bubble. Returns {cam_id: device_uuid}."""
    headers = _supabase_headers(key)
    return_headers = {**headers, "Prefer": "return=representation"}
    result: dict[int, str] = {}
    for c in CAM_CONFIG:
        name = c["label"]
        try:
            r = req.get(
                f"{sb_url}/rest/v1/devices?select=id&bubble=eq.{bubble_id}&name=eq.{name.replace(' ', '%20')}&limit=1",
                headers=headers,
                timeout=10,
            )
            r.raise_for_status()
            rows = r.json()
            if rows:
                result[c["id"]] = rows[0]["id"]
                continue
        except Exception as e:
            print(f"[Bootstrap] Lookup failed for {name}: {e}")
            continue

        token = f"SIMCAM{c['id']}{bubble_id.replace('-', '')[:8].upper()}"
        payload = {
            "bubble": bubble_id,
            "name": name,
            "placement": c["placement"],
            "contact": "",
            "device_token": token,
            "status": "online",
        }
        try:
            ir = req.post(
                f"{sb_url}/rest/v1/devices",
                headers=return_headers,
                json=payload,
                timeout=10,
            )
            ir.raise_for_status()
            device_id = ir.json()[0]["id"]
            result[c["id"]] = device_id
            print(f"[Bootstrap] Created {name} = {device_id}")
        except Exception as e:
            resp_text = getattr(e, "response", None) and e.response.text
            print(f"[Bootstrap] Insert failed for {name}: {e} — {resp_text}")
    return result


# ── Annotation + scoring ──────────────────────────────────────────────────────


def annotate_frame(frame, detections, suspicion: float, label: str):
    out = frame.copy()
    h, w = out.shape[:2]
    bar_color = (
        (0, 200, 0) if suspicion < 0.4 else (0, 140, 255) if suspicion < 0.7 else (0, 0, 220)
    )
    for (box, conf) in detections:
        x1, y1, x2, y2 = box
        cv2.rectangle(out, (x1, y1), (x2, y2), bar_color, 2)
        txt = f"person {conf:.0%}"
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(out, (x1, max(0, y1 - th - 4)), (x1 + tw + 4, y1), bar_color, -1)
        cv2.putText(out, txt, (x1 + 2, y1 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    bar_w = int(w * 0.35)
    bar_h = 16
    bx, by = 12, 12
    filled = int(bar_w * suspicion)
    cv2.rectangle(out, (bx, by), (bx + bar_w, by + bar_h), (40, 40, 40), -1)
    if filled > 0:
        cv2.rectangle(out, (bx, by), (bx + filled, by + bar_h), bar_color, -1)
    cv2.rectangle(out, (bx, by), (bx + bar_w, by + bar_h), (120, 120, 120), 1)
    cv2.putText(
        out,
        f"{label}  SUS {suspicion:.0%}",
        (bx + bar_w + 8, by + 13),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (220, 220, 220),
        1,
    )
    return out


def score_suspicion(detections, prev_persons: int, motion: float) -> tuple[float, int]:
    persons = [d for d in detections if d[1] >= 0.30]
    n = len(persons)
    score = 0.0
    if n >= 1:
        score += 0.32
    if n >= 2:
        score += 0.18
    if n > prev_persons:
        score += 0.12  # someone appeared / moved into frame
    score += min(0.30, motion * 2.0)
    if motion >= 0.06:
        score += 0.10
    max_conf = max((c for (_, c) in persons), default=0.0)
    if max_conf >= 0.55:
        score += 0.08
    if max_conf >= 0.75:
        score += 0.08
    return min(score, 1.0), n


def detect_persons_locked(frame):
    with _DETECTOR_LOCK:
        return find_person_detections(frame)


# ── Escalation pipeline ───────────────────────────────────────────────────────


def push_event(
    sb_url: str,
    key: str,
    bubble_id: str,
    device_id: str,
    cam_cfg: dict,
    score: float,
    replay_url: str | None,
    crop_url: str | None,
    profile: dict,
) -> None:
    headers = {**_supabase_headers(key), "Prefer": "return=representation"}
    row = {
        "bubble": bubble_id,
        "device": device_id,
        "event_type": "suspicious_person",
        "event_subtype": "live_simulation",
        "risk_level": "high" if score >= 0.8 else "medium" if score >= 0.5 else "low",
        "confidence": round(float(score), 4),
        "incident_confirmed": True,
        "metadata": {
            "source": cam_cfg["video"],
            "camera_label": cam_cfg["label"],
            "replay_url": replay_url,
            "profile_crop_url": crop_url,
            "character_profile": profile or {},
        },
    }
    try:
        r = req.post(f"{sb_url}/rest/v1/device_events", headers=headers, json=row, timeout=10)
        r.raise_for_status()
        print(f"[Event] {cam_cfg['label']} → device_events inserted (score={score:.2f})")
    except Exception as e:
        resp_text = getattr(e, "response", None) and e.response.text
        print(f"[Event] Insert failed for {cam_cfg['label']}: {e} — {resp_text}")


def insert_character(sb_url: str, key: str, profile: dict, crop_url: str | None, cropped) -> None:
    if not crop_url or cropped is None:
        return
    if is_duplicate_character(profile or {}, cropped, sb_url, key):
        return
    headers = {**_supabase_headers(key), "Prefer": "return=representation"}
    row = {
        "sus_character_description": (profile or {}).get("summary", ""),
        "profile_crop_url": crop_url,
    }
    try:
        r = req.post(f"{sb_url}/rest/v1/characters", headers=headers, json=row, timeout=10)
        r.raise_for_status()
        print(f"[Character] Inserted: {r.json()[0]['id']}")
    except Exception as e:
        print(f"[Character] Insert failed: {e}")


def handle_escalation(
    cam_cfg: dict,
    device_id: str,
    bubble_id: str,
    sb_url: str,
    sb_key: str,
    score: float,
    buffered: list,
    best: dict,
) -> None:
    ts = int(time.time())
    print(f"[Escalate] {cam_cfg['label']} score={score:.2f} ts={ts}")

    replay_url: str | None = None
    if buffered:
        first_frame = buffered[0][0]
        h, w = first_frame.shape[:2]
        replay_dir = ROOT / "storage" / "clips" / "sim_replay"
        replay_dir.mkdir(parents=True, exist_ok=True)
        replay_path = str(replay_dir / f"{cam_cfg['label'].replace(' ', '_')}_{ts}.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"avc1")
        writer = cv2.VideoWriter(replay_path, fourcc, 24.0, (w, h))
        for (frm, dets, sus) in buffered:
            writer.write(annotate_frame(frm, dets, sus, cam_cfg["label"]))
        writer.release()
        replay_url = upload_replay_to_storage(replay_path, ts)

    cropped = crop_person(best["frame"], best["bbox"]) if best.get("frame") is not None else None
    crop_url = upload_crop_to_storage(cropped, ts) if cropped is not None else None
    profile = analyze_suspect(cropped) if cropped is not None else {}

    push_event(sb_url, sb_key, bubble_id, device_id, cam_cfg, score, replay_url, crop_url, profile)
    insert_character(sb_url, sb_key, profile, crop_url, cropped)


# ── Per-camera worker thread ──────────────────────────────────────────────────


def run_cam_worker(
    cam_cfg: dict,
    device_id: str,
    bubble_id: str,
    sb_url: str,
    sb_key: str,
) -> None:
    video_path = str(ROOT / cam_cfg["video"])
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[Worker {cam_cfg['label']}] Could not open {video_path}")
        return

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total <= 0:
        print(f"[Worker {cam_cfg['label']}] empty video")
        cap.release()
        return

    stride = FRAME_STRIDE
    target_period = stride / (PLAYBACK_SPEED * src_fps)  # wall-seconds per emitted frame
    buffer: deque = deque(maxlen=max(8, int((src_fps / stride) * BUFFER_SECONDS)))
    best = {"score": 0.0, "frame": None, "bbox": None}
    last_escalate = 0.0
    prev_persons = 0
    prev_gray = None
    frame_idx = 0
    emit_idx = 0
    last_detections: list = []

    print(
        f"[Worker {cam_cfg['label']}] {video_path}  src={src_fps:.0f}fps total={total} "
        f"period={target_period * 1000:.0f}ms"
    )

    try:
        while ACTIVE.is_set():
            t0 = time.monotonic()
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                frame_idx = 0
                continue

            if emit_idx % INFER_EVERY == 0:
                last_detections = detect_persons_locked(frame)
            detections = last_detections

            # cheap motion estimate
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            motion = 0.0
            if prev_gray is not None and prev_gray.shape == gray.shape:
                diff = cv2.absdiff(prev_gray, gray)
                motion = float(diff.mean()) / 255.0
            prev_gray = gray

            score, n = score_suspicion(detections, prev_persons, motion)
            prev_persons = n

            for ((x1, y1, x2, y2), conf) in detections:
                clarity = compute_clarity_score(frame, (x1, y1, x2, y2), conf)
                if clarity > best["score"]:
                    best = {"score": clarity, "frame": frame.copy(), "bbox": (x1, y1, x2, y2)}

            annotated = annotate_frame(frame, detections, score, cam_cfg["label"])
            buffer.append((frame.copy(), detections, score))

            ok_enc, jpg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ok_enc:
                STORES[cam_cfg["id"]].put(jpg.tobytes())

            now = time.time()
            if (
                score >= ESCALATE_THRESHOLD
                and (now - last_escalate) > ESCALATE_COOLDOWN_S
                and best["frame"] is not None
            ):
                last_escalate = now
                buffered_copy = list(buffer)
                best_copy = best.copy()
                best = {"score": 0.0, "frame": None, "bbox": None}
                threading.Thread(
                    target=handle_escalation,
                    args=(cam_cfg, device_id, bubble_id, sb_url, sb_key, score, buffered_copy, best_copy),
                    daemon=True,
                ).start()

            frame_idx += stride
            if frame_idx >= total:
                frame_idx = 0
            emit_idx += 1

            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, target_period - elapsed))
    finally:
        cap.release()


# ── Entrypoint ────────────────────────────────────────────────────────────────


def main() -> None:
    sb_url = os.environ.get("VITE_SUPABASE_URL")
    sb_key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not sb_url or not sb_key:
        print("[Setup] VITE_SUPABASE_URL or SUPABASE_SERVICE_KEY missing — add them to .env")
        return

    bubble_id = resolve_bubble_id(sb_url, sb_key)
    if not bubble_id:
        print("[Setup] No bubble id available — create a bubble first or set BUBBLE_ID")
        return
    print(f"[Setup] Using bubble {bubble_id}")

    devices = ensure_sim_devices(sb_url, sb_key, bubble_id)
    if len(devices) != len(CAM_CONFIG):
        print("[Setup] Could not provision all sim devices — aborting")
        return

    missing_videos = [c["video"] for c in CAM_CONFIG if not (ROOT / c["video"]).exists()]
    if missing_videos:
        print(f"[Setup] Missing videos: {missing_videos}")
        return

    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), _Handler)
    ACTIVE.set()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[Server] MJPEG up on http://localhost:{PORT}/stream/<1-4>")

    for c in CAM_CONFIG:
        t = threading.Thread(
            target=run_cam_worker,
            args=(c, devices[c["id"]], bubble_id, sb_url, sb_key),
            daemon=True,
        )
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Server] Shutting down…")
        ACTIVE.clear()
        server.shutdown()


if __name__ == "__main__":
    main()
