"""
Lightweight YOLO MJPEG server.

Spins up an HTTP server on MJPEG_PORT, runs YOLO on a video file,
streams annotated frames, then shuts down cleanly when the video ends.

Can be imported and called from other scripts:
    from scripts.yolo_watch import stream_video
    stream_video('videos/nishan-kidnap.MOV')   # blocks until done

Or run directly:
    python scripts/yolo_watch.py videos/nishan-kidnap.MOV
"""
import http.server
import json
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MJPEG_PORT = 8765

# ── Shared frame store ────────────────────────────────────────────────────────

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


_store = _FrameStore()
_active = threading.Event()   # set while video is playing


# ── HTTP handler ──────────────────────────────────────────────────────────────

class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/stream'):
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                while _active.is_set():
                    frame = _store.get()
                    if frame is None:
                        time.sleep(0.05)
                        continue
                    try:
                        self.wfile.write(
                            b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
                        )
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        break
                    time.sleep(1 / 15)
            except Exception:
                pass

        elif self.path.startswith('/status'):
            body = json.dumps({'active': _active.is_set()}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_error(404)

    def log_message(self, *_args):
        pass  # silence per-request logs


# ── Colors for YOLO class labels ──────────────────────────────────────────────

_COLORS = [
    (0, 255, 0), (255, 80, 80), (80, 80, 255), (255, 165, 0),
    (128, 0, 200), (0, 220, 220), (220, 0, 220), (0, 140, 255),
]
_HIGH_RISK = {"person", "knife", "scissors", "cell phone", "backpack", "handbag"}


def _annotate(frame: np.ndarray, results, suspicion: float) -> np.ndarray:
    out = frame.copy()
    h, w = out.shape[:2]

    for box in results[0].boxes:
        x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].cpu().numpy())
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        label = results[0].names[cls]
        color = _COLORS[cls % len(_COLORS)]
        thickness = 3 if label in _HIGH_RISK else 2
        cv2.rectangle(out, (x1, y1), (x2, y2), color, thickness)
        txt = f"{label} {conf:.0%}"
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(out, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(out, txt, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)

    # Suspicion bar
    bar_w = int(w * 0.35)
    bar_h = 18
    bx, by = 12, 12
    filled = int(bar_w * suspicion)
    bar_color = (0, 200, 0) if suspicion < 0.4 else (0, 140, 255) if suspicion < 0.7 else (0, 0, 220)
    cv2.rectangle(out, (bx, by), (bx + bar_w, by + bar_h), (40, 40, 40), -1)
    if filled > 0:
        cv2.rectangle(out, (bx, by), (bx + filled, by + bar_h), bar_color, -1)
    cv2.rectangle(out, (bx, by), (bx + bar_w, by + bar_h), (120, 120, 120), 1)
    cv2.putText(out, f"SUSPICION {suspicion:.0%}", (bx + bar_w + 8, by + 13),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    cv2.putText(out, "ATLAS AI", (w - 90, h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 50), 1)
    return out


# ── Public API ────────────────────────────────────────────────────────────────

def start_server(port: int = MJPEG_PORT) -> "http.server.ThreadingHTTPServer":
    """Start the MJPEG server and return it. Caller must call stop_server() when done."""
    server = http.server.ThreadingHTTPServer(('0.0.0.0', port), _Handler)
    _active.set()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f'[YoloWatch] MJPEG server started on http://localhost:{port}/stream')
    return server


def stop_server(server: "http.server.ThreadingHTTPServer") -> None:
    """Signal the stream as ended and shut down the server."""
    _active.clear()
    server.shutdown()
    print('[YoloWatch] Stream ended.')


def push_frame(jpeg_bytes: bytes) -> None:
    """Push an already-encoded JPEG frame into the live stream."""
    _store.put(jpeg_bytes)


def stream_video(video_path: str, port: int = MJPEG_PORT) -> None:
    """Process video_path with YOLO and stream via MJPEG until the video ends."""
    from ultralytics import YOLO as _YOLO
    model = _YOLO('yolov8n.pt')

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video: {video_path}')

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    server = http.server.ThreadingHTTPServer(('0.0.0.0', port), _Handler)
    _active.set()
    srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
    srv_thread.start()
    print(f'[YoloWatch] Streaming on http://localhost:{port}/stream  ({total} frames @ {fps:.0f}fps)')

    start = time.monotonic()
    try:
        while True:
            elapsed = time.monotonic() - start
            target = int(elapsed * fps)
            if target >= total:
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
            ret, frame = cap.read()
            if not ret:
                break

            results = model(frame, conf=0.35, verbose=False)
            person_count = sum(1 for b in results[0].boxes if results[0].names[int(b.cls[0])] == 'person')
            sus_labels = sum(1 for b in results[0].boxes if results[0].names[int(b.cls[0])] in _HIGH_RISK)
            suspicion = min(1.0, 0.35 * person_count + 0.15 * sus_labels)

            annotated = _annotate(frame, results, suspicion)
            ok, buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 78])
            if ok:
                _store.put(buf.tobytes())

            # Sleep only the remaining budget so output stays near real-time
            spent = time.monotonic() - start - elapsed
            time.sleep(max(0.0, (1 / 15) - spent))
    finally:
        cap.release()
        _active.clear()
        server.shutdown()
        print('[YoloWatch] Stream ended.')


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / 'videos' / 'nishan-kidnap.MOV')
    stream_video(path)
