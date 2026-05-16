from typing import List, Dict, Any
import numpy as np
import logging
from backend.utils.logger import get_logger

logger = get_logger("yolo")

try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

class YoloDetector:
    def __init__(self, model_path: str = "yolov8n.pt", device: str = "cpu"):
        self.model_path = model_path
        self.device = device
        self.model = None

    def load(self):
        if YOLO is None:
            raise RuntimeError("ultralytics YOLO not installed")
        logging.getLogger("ultralytics").setLevel(logging.ERROR)
        logging.getLogger("ultralytics.yolo").setLevel(logging.ERROR)
        self.model = YOLO(self.model_path)
        logger.info("Loaded YOLO model %s", self.model_path)

    def predict(self, frame: np.ndarray, conf: float = 0.35) -> List[Dict[str, Any]]:
        if self.model is None:
            self.load()
        # ultralytics returns results with boxes
        results = self.model.predict(frame, imgsz=640, conf=conf, verbose=False, device=self.device)
        out = []
        for r in results:
            for box in r.boxes:
                cls = int(box.cls.cpu().numpy()) if hasattr(box, 'cls') else None
                confv = float(box.conf.cpu().numpy()) if hasattr(box, 'conf') else 0.0
                xyxy = box.xyxy.cpu().numpy().tolist() if hasattr(box, 'xyxy') else []
                out.append({"class": cls, "score": confv, "bbox": xyxy})
        return out
