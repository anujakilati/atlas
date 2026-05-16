from fastapi import APIRouter, UploadFile, File, BackgroundTasks, WebSocket, HTTPException, Query
from fastapi.responses import StreamingResponse
from backend.pipelines.pipeline import CCTVPipeline
from backend.reports.generator import generate_report, report_markdown
from backend.config import CONFIG
from backend.utils.logger import get_logger
import asyncio
import os
import sys
import subprocess
import time
import cv2
import numpy as np

router = APIRouter()
logger = get_logger("api")

_pipeline_tasks = {}

@router.post('/upload')
async def upload_video(file: UploadFile = File(...)):
    dest = f"./uploads/{file.filename}"
    import os
    os.makedirs('./uploads', exist_ok=True)
    with open(dest, 'wb') as f:
        f.write(await file.read())
    return {"path": dest}



_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@router.get('/videos')
def list_videos():
    vdir = os.path.join(_PROJECT_ROOT, 'videos')
    if not os.path.isdir(vdir):
        return {'videos': []}
    files = [f for f in os.listdir(vdir) if os.path.isfile(os.path.join(vdir, f))]
    return {'videos': sorted(files)}


@router.post('/replay')
def make_replay():
    """Run the local replay generator script to create a replay for the latest event.
    Returns the path of the generated replay if available.
    """
    script = os.path.join('.', 'scripts', 'show_latest_event.py')
    if not os.path.exists(script):
        raise HTTPException(status_code=500, detail='replay script not found')

    # run script synchronously and wait briefly for output file
    try:
        subprocess.check_call([sys.executable, script])
    except Exception:
        # try running without opening (script is quiet) but ignore errors
        pass

    # look for the most recent replay file
    rdir = os.path.join('.', 'storage', 'clips', 'replay')
    if not os.path.isdir(rdir):
        raise HTTPException(status_code=404, detail='no replay directory')
    files = [os.path.join(rdir, f) for f in os.listdir(rdir) if f.endswith('.mp4')]
    if not files:
        raise HTTPException(status_code=404, detail='no replay files')
    latest = max(files, key=os.path.getmtime)
    # Return a URL path under /storage so the UI can open it
    rel = os.path.relpath(latest, start=os.path.join('.', 'storage'))
    url_path = '/storage/' + rel.replace(os.sep, '/')
    return {'replay': url_path}

@router.post('/analyze')
async def analyze_stream(source: str):
    # start pipeline in background
    loop = asyncio.get_event_loop()
    pipe = CCTVPipeline(source)
    task = loop.create_task(pipe.run())
    _pipeline_tasks[source] = task
    return {"status": "started", "source": source}

@router.get('/events')
async def get_events(limit: int = 100):
    return generate_report(limit=limit)

_sim_process: subprocess.Popen | None = None

@router.post('/simulate')
def start_simulation(background_tasks: BackgroundTasks):
    """Run batch analysis on the kidnapping video then generate the YOLO replay stream."""
    global _sim_process
    if _sim_process and _sim_process.poll() is None:
        return {'status': 'already_running'}

    video = os.path.join(_PROJECT_ROOT, 'videos', 'nishan-kidnap.MOV')
    if not os.path.isfile(video):
        raise HTTPException(status_code=404, detail='nishan-kidnap.MOV not found in ./videos/')

    python = sys.executable

    def _run():
        global _sim_process
        # Step 1: batch analysis populates the local event DB
        subprocess.run([python, 'main.py', '--batch', '--video', video], cwd=_PROJECT_ROOT)
        # Step 2: generate replay + stream via YOLO MJPEG server
        _sim_process = subprocess.Popen(
            [python, 'scripts/show_latest_event.py', '--source', video],
            cwd=_PROJECT_ROOT,
        )

    background_tasks.add_task(_run)
    return {'status': 'started'}


@router.get('/simulate/status')
def simulation_status():
    running = _sim_process is not None and _sim_process.poll() is None
    return {'running': running}


@router.websocket('/ws/alerts')
async def ws_alerts(ws: WebSocket):
    await ws.accept()
    # simple demo: stream DB events periodically
    import time
    while True:
        rep = generate_report(limit=10)
        await ws.send_json(rep['summary'])
        await asyncio.sleep(5)


# YOLO class colors (BGR) — one per class index mod len
_COLORS = [
    (0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 165, 0),
    (128, 0, 128), (0, 255, 255), (255, 0, 255), (0, 128, 255),
]

# Suspicion heuristic labels treated as high-risk
_SUSPICIOUS_LABELS = {"person", "backpack", "handbag", "suitcase", "knife", "scissors"}

_yolo_model = None

def _get_yolo():
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        _yolo_model = YOLO("yolov8n.pt")
    return _yolo_model


def _annotate_frame(frame: np.ndarray, detections, suspicion: float) -> np.ndarray:
    out = frame.copy()
    h, w = out.shape[:2]

    for det in detections:
        x1, y1, x2, y2 = det["box"]
        label = det["label"]
        conf = det["conf"]
        color = _COLORS[det["cls"] % len(_COLORS)]
        is_sus = label in _SUSPICIOUS_LABELS

        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2 if not is_sus else 3)
        txt = f"{label} {conf:.0%}"
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(out, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(out, txt, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)

    # HUD: suspicion bar
    bar_w = int(w * 0.35)
    bar_h = 18
    bx, by = 12, 12
    filled = int(bar_w * suspicion)
    bar_color = (0, 255, 0) if suspicion < 0.4 else (0, 165, 255) if suspicion < 0.7 else (0, 0, 255)
    cv2.rectangle(out, (bx, by), (bx + bar_w, by + bar_h), (50, 50, 50), -1)
    if filled > 0:
        cv2.rectangle(out, (bx, by), (bx + filled, by + bar_h), bar_color, -1)
    cv2.rectangle(out, (bx, by), (bx + bar_w, by + bar_h), (150, 150, 150), 1)
    cv2.putText(out, f"SUSPICION {suspicion:.0%}", (bx + bar_w + 8, by + 13),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

    # ATLAS watermark
    cv2.putText(out, "ATLAS AI", (w - 90, h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 60), 1)

    return out


async def _mjpeg_generator(video_path: str):
    """Yield MJPEG boundary frames locked to wall-clock time so playback is always real-time."""
    model = _get_yolo()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total_frames <= 0:
        cap.release()
        return

    # Output at a fixed rate YOLO can comfortably sustain; the source frame
    # position is derived from elapsed wall-clock time so the video never drifts.
    OUTPUT_FPS = 15.0
    output_interval = 1.0 / OUTPUT_FPS

    start_wall = time.monotonic()

    try:
        while True:
            t0 = time.monotonic()
            elapsed = t0 - start_wall

            # Which source frame should we be showing right now?
            target = int(elapsed * fps) % total_frames
            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
            ret, frame = cap.read()
            if not ret:
                start_wall = time.monotonic()
                continue

            results = model(frame, conf=0.35, verbose=False)
            detections = []
            person_count = 0
            sus_label_count = 0
            for box in results[0].boxes:
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].cpu().numpy())
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                label = model.names[cls]
                detections.append({"box": (x1, y1, x2, y2), "cls": cls, "label": label, "conf": conf})
                if label == "person":
                    person_count += 1
                if label in _SUSPICIOUS_LABELS:
                    sus_label_count += 1

            suspicion = min(1.0, 0.3 * person_count + 0.15 * sus_label_count)
            annotated = _annotate_frame(frame, detections, suspicion)

            ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if not ok:
                continue
            jpeg = buf.tobytes()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            )

            # Sleep only for the remaining budget of this output frame slot.
            spent = time.monotonic() - t0
            sleep_for = max(0.0, output_interval - spent)
            await asyncio.sleep(sleep_for)
    finally:
        cap.release()


@router.get("/yolo-stream")
async def yolo_stream(video: str = Query(..., description="Video filename inside ./videos/")):
    vdir = os.path.join(_PROJECT_ROOT, "videos")
    # Sanitize: strip path separators so callers can't escape the videos dir
    safe_name = os.path.basename(video)
    video_path = os.path.join(vdir, safe_name)
    if not os.path.isfile(video_path):
        raise HTTPException(status_code=404, detail=f"Video not found: {safe_name}")

    return StreamingResponse(
        _mjpeg_generator(video_path),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
