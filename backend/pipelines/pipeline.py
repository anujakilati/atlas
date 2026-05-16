import asyncio
import time
from backend.ingestion.ingester import VideoIngester
from backend.detectors.yolo_detector import YoloDetector
from backend.trackers.tracker import TrackerWrapper
from backend.storage.storage import save_frame
from backend.storage import db
from backend.config import CONFIG
from backend.utils.logger import get_logger

logger = get_logger("pipeline")

class CCTVPipeline:
    def __init__(self, source: str, model_path: str = None, device: str = "cpu"):
        self.source = source
        self.frame_q = asyncio.Queue(maxsize=CONFIG.get('ingestion', {}).get('max_frame_queue', 256))
        self.detector = YoloDetector(model_path or CONFIG.get('YOLO_MODEL', 'yolov8n.pt'), device=device)
        self.tracker = TrackerWrapper()
        self.vlm_q = asyncio.Queue()

    async def run(self):
        ensure = CONFIG.get('storage', {})
        from backend.storage.storage import ensure_dirs
        ensure_dirs(CONFIG)
        db.init_db(CONFIG['storage']['db_path'])
        ing = VideoIngester(self.source, target_fps=CONFIG.get('ingestion', {}).get('default_fps', 5))
        producer = asyncio.create_task(ing.start(self.frame_q))
        consumer = asyncio.create_task(self.consume())
        await asyncio.gather(producer, consumer)

    async def consume(self):
        while True:
            ts, frame_idx, src_fps, frame = await self.frame_q.get()
            if ts is None and frame is None:
                break
            detections = self.detector.predict(frame, conf=CONFIG.get('detection', {}).get('conf_threshold', 0.35))
            dets_for_tracking = []
            for d in detections:
                xyxy = d['bbox']
                score = d['score']
                dets_for_tracking.append([xyxy[0][0], xyxy[0][1], xyxy[0][2], xyxy[0][3], score, d.get('class')])
            tracks = self.tracker.update(dets_for_tracking, frame)
            # simple suspicious filter: person class (class id 0) with high score
            for t in tracks:
                if t.get('det_class') == 0 or True:
                    # create event
                    path = save_frame(frame, CONFIG['storage']['frames_dir'], prefix="susp")
                    event = {"ts": ts, "label": "suspicious", "score": 0.9, "bbox": t.get('bbox'), "frame_path": path, "clip_path": None, "meta": {"track": t, "source": self.source, "frame_index": frame_idx, "source_fps": src_fps}}
                    db.insert_event(CONFIG['storage']['db_path'], event)
                    await self.vlm_q.put(event)
        await self.vlm_q.put(None)
