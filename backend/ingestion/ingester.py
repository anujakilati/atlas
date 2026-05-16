import cv2
import time
import asyncio
from backend.utils.logger import get_logger

logger = get_logger("ingester")

class VideoIngester:
    def __init__(self, source: str, target_fps: int = 5, max_queue: int = 256):
        self.source = source
        self.target_fps = target_fps
        self.max_queue = max_queue
        self.cap = None

    async def start(self, frame_queue: asyncio.Queue):
        loop = asyncio.get_event_loop()
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            logger.error("Unable to open source %s", self.source)
            return
        fps = self.cap.get(cv2.CAP_PROP_FPS) or 10
        skip = max(1, int(fps / max(0.1, self.target_fps)))
        idx = 0
        logger.info("Ingesting %s at target_fps=%s skip=%s", self.source, self.target_fps, skip)
        while True:
            ret, frame = await loop.run_in_executor(None, self.cap.read)
            if not ret:
                break
            if idx % skip == 0:
                if frame_queue.qsize() < self.max_queue:
                    await frame_queue.put((time.time(), idx, fps, frame))
            idx += 1
            await asyncio.sleep(0)
        self.cap.release()
        await frame_queue.put((None, None, None, None))
