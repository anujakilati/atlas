from dataclasses import dataclass
import numpy as np
from ultralytics import YOLO


@dataclass
class Detection:
    cls: int
    label: str
    conf: float
    box: tuple[int, int, int, int]   # x1 y1 x2 y2
    center: tuple[int, int]


class YOLODetector:
    def __init__(self, weights="yolov8n.pt", conf=0.40):
        self.model = YOLO(weights)
        self.conf  = conf

    def detect(self, frame: np.ndarray) -> list[Detection]:
        results = self.model(frame, conf=self.conf, verbose=False)
        out = []
        if not results:
            return out
        for box in results[0].boxes:
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].cpu().numpy())
            cls  = int(box.cls[0])
            conf = float(box.conf[0])
            out.append(Detection(
                cls=cls,
                label=self.model.names[cls],
                conf=conf,
                box=(x1, y1, x2, y2),
                center=((x1+x2)//2, (y1+y2)//2),
            ))
        return out

    @property
    def names(self):
        return self.model.names
