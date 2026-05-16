import asyncio
import cv2
import time
import os
from collections import deque
from typing import Deque, Tuple, List, Dict, Any
import numpy as np
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort

from ..config import settings
from ..ws import manager
from ..db import AsyncSessionLocal
from .. import models


class CameraWorker:
    def __init__(self, camera_id: int, url: str, name: str = None):
        self.camera_id = camera_id
        self.url = url
        self.name = name or f"camera-{camera_id}"
        self.buffer: Deque[Tuple[float, np.ndarray]] = deque(maxlen=int(settings.BUFFER_SECONDS * 30))
        self.model = YOLO(settings.YOLO_MODEL_PATH)
        self.tracker = DeepSort(max_age=30)
        self.bg_sub = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=16, detectShadows=True)
        self.running = False
        self.capture = None

    async def start(self):
        self.running = True
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run)

    def stop(self):
        self.running = False
        if self.capture:
            try:
                self.capture.release()
            except Exception:
                pass

    def _run(self):
        self.capture = cv2.VideoCapture(self.url)
        if not self.capture.isOpened():
            asyncio.run(self._report_status('OFFLINE'))
            return
        asyncio.run(self._report_status('ONLINE'))

        fps = max(1, int(self.capture.get(cv2.CAP_PROP_FPS) or 15))
        frame_idx = 0
        post_event_counter = 0
        event_active = False
        event_frames: List[np.ndarray] = []

        while self.running:
            ok, frame = self.capture.read()
            if not ok or frame is None:
                # disconnected or no frame
                asyncio.run(self._report_status('NO_SIGNAL'))
                time.sleep(1)
                # try reconnect
                self.capture.release()
                time.sleep(2)
                self.capture = cv2.VideoCapture(self.url)
                continue

            frame_idx += 1
            timestamp = time.time()
            # health: detect frozen (compare to previous frame)
            self.buffer.append((timestamp, frame.copy()))

            if frame_idx % settings.PROCESS_EVERY_NTH_FRAME != 0:
                continue

            # motion detection
            mask = self.bg_sub.apply(frame)
            motion_ratio = (mask > 0).sum() / (mask.shape[0] * mask.shape[1])
            if motion_ratio < settings.MOTION_SENSITIVITY:
                # no significant motion
                if event_active:
                    post_event_counter += 1
                    event_frames.append(frame.copy())
                    # after enough post frames, finalize
                    if post_event_counter > settings.POST_EVENT_SECONDS * (fps / settings.PROCESS_EVERY_NTH_FRAME):
                        self._finalize_event(event_frames)
                        event_active = False
                        event_frames = []
                        post_event_counter = 0
                continue

            # motion exceeded threshold -> run detection
            results = self.model.predict(frame, imgsz=640, conf=0.35, classes=None, verbose=False)
            detections = []
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    xyxy = box.xyxy[0].cpu().numpy().tolist()
                    conf = float(box.conf[0].cpu().numpy())
                    cls = int(box.cls[0].cpu().numpy())
                    label = self.model.names.get(cls, str(cls))
                    # filter to allowed classes
                    if label not in ["person", "car", "truck", "bus", "bicycle", "motorbike", "bag", "suitcase"]:
                        continue
                    x1, y1, x2, y2 = map(int, xyxy)
                    detections.append((x1, y1, x2 - x1, y2 - y1, conf, label))

            if detections:
                # update tracker
                tracks = self.tracker.update_tracks(detections, frame=frame)
                # draw overlays
                for tr in tracks:
                    if not tr.is_confirmed():
                        continue
                    tid = tr.track_id
                    l = tr.get_det_confidence()
                    lbox = tr.to_ltrb()  # left, top, right, bottom
                    x1, y1, x2, y2 = map(int, lbox)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"id:{tid}", (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                # start or extend event
                event_active = True
                post_event_counter = 0
                event_frames.append(frame.copy())
                # send realtime alert
                asyncio.run(manager.broadcast({
                    "type": "suspicious_motion",
                    "camera_id": self.camera_id,
                    "timestamp": time.time(),
                    "detections": [dict(label=tr.det_class if hasattr(tr, 'det_class') else 'obj', track_id=tr.track_id) for tr in tracks]
                }))

        # cleanup
        try:
            self.capture.release()
        except Exception:
            pass

    def _finalize_event(self, frames: List[np.ndarray]):
        # gather pre-buffer frames (PRE_EVENT_SECONDS)
        pre_frames = []
        need = int(settings.PRE_EVENT_SECONDS * 30)
        for ts, f in list(self.buffer)[-need:]:
            pre_frames.append(f)

        all_frames = pre_frames + frames
        # write frames to mp4 with overlays
        outdir = os.path.abspath(settings.STORAGE_PATH)
        os.makedirs(outdir, exist_ok=True)
        filename = f"event_{int(time.time())}.mp4"
        outpath = os.path.join(outdir, filename)
        h, w = all_frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(outpath, fourcc, 15.0, (w, h))
        for f in all_frames:
            writer.write(f)
        writer.release()

        # create thumbnail
        thumb_path = outpath.replace('.mp4', '.jpg')
        cv2.imwrite(thumb_path, all_frames[len(pre_frames)])

        # persist to DB
        async def _save():
            async with AsyncSessionLocal() as session:
                moment = models.SuspiciousMoment(
                    camera_id=self.camera_id,
                    event_type='motion_detected',
                    confidence=1.0,
                    thumbnail_path=thumb_path,
                    video_path=outpath,
                    meta={}
                )
                session.add(moment)
                await session.commit()
        try:
            asyncio.run(_save())
        except Exception:
            pass

    async def _report_status(self, status: str):
        await manager.broadcast({"type": "camera_status", "camera_id": self.camera_id, "status": status})
