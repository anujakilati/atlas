#!/usr/bin/env python3
"""Load latest event, annotate the original video around the suspicious frame,
save the replay clip, open it, and print a short report."""
import ast
import contextlib
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path so `backend` package imports work when
# running the script directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.storage import db
from backend.config import CONFIG
from backend.utils.logger import get_logger
import cv2
import numpy as np

logger = get_logger('show_event')


def open_replay(path):
    if os.name == 'posix':
        opener = 'open' if os.uname().sysname == 'Darwin' else 'xdg-open'
        os.system(f'{opener} "{path}" >/dev/null 2>&1 &')


def find_person_bbox(frame):
    """Return the largest person bbox in the frame using YOLO if available."""
    try:
        from backend.detectors.yolo_detector import YoloDetector
    except Exception:
        return None

    detector = find_person_bbox._detector if hasattr(find_person_bbox, "_detector") else None
    if detector is None:
        detector = YoloDetector('yolov8n.pt', device='cpu')
        find_person_bbox._detector = detector

    with contextlib.redirect_stdout(open(os.devnull, 'w')), contextlib.redirect_stderr(open(os.devnull, 'w')):
        detections = detector.predict(frame, conf=0.25)
    best = None
    best_area = 0
    for det in detections:
        if det.get('class') != 0:
            continue
        bbox = det.get('bbox') or []
        if bbox and isinstance(bbox[0], (list, tuple)):
            x1, y1, x2, y2 = map(int, bbox[0])
        elif len(bbox) >= 4:
            x1, y1, x2, y2 = map(int, bbox[:4])
        else:
            continue
        area = max(0, x2 - x1) * max(0, y2 - y1)
        if area > best_area:
            best_area = area
            best = (x1, y1, x2, y2)
    return best


def find_orange_object_bbox(frame):
    """Find a prominent orange object blob in the lower-middle portion of the frame."""
    h, w = frame.shape[:2]
    roi = frame[int(h * 0.35):h, int(w * 0.15):int(w * 0.85)]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # Orange snack bag is highly saturated and warm-colored in the reviewed clip.
    lower1 = np.array([5, 80, 80])
    upper1 = np.array([25, 255, 255])
    mask = cv2.inRange(hsv, lower1, upper1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 400:
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        # shift back into frame coordinates
        return (x + int(w * 0.15), y + int(h * 0.35), x + int(w * 0.15) + bw, y + int(h * 0.35) + bh)
    return None


def draw_marks(frame, person_bbox=None, object_bbox=None, label='suspicious'):
    out = frame.copy()
    if person_bbox is not None:
        x1, y1, x2, y2 = person_bbox
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 3)
        cv2.putText(out, 'person', (x1, max(20, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
    cv2.putText(out, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    return out


def bbox_iou(a, b):
    if a is None or b is None:
        return 0.0
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def find_person_bboxes(frame):
    """Return all person bboxes in the frame using YOLO if available."""
    try:
        from backend.detectors.yolo_detector import YoloDetector
    except Exception:
        return []

    detector = find_person_bboxes._detector if hasattr(find_person_bboxes, "_detector") else None
    if detector is None:
        detector = YoloDetector('yolov8n.pt', device='cpu')
        find_person_bboxes._detector = detector

    with contextlib.redirect_stdout(open(os.devnull, 'w')), contextlib.redirect_stderr(open(os.devnull, 'w')):
        detections = detector.predict(frame, conf=0.25)
    boxes = []
    for det in detections:
        if det.get('class') != 0:
            continue
        bbox = det.get('bbox') or []
        if bbox and isinstance(bbox[0], (list, tuple)):
            x1, y1, x2, y2 = map(int, bbox[0])
        elif len(bbox) >= 4:
            x1, y1, x2, y2 = map(int, bbox[:4])
        else:
            continue
        boxes.append((x1, y1, x2, y2))
    return boxes


def main():
    dpath = CONFIG['storage']['db_path']
    events = db.list_events(dpath, limit=1)
    if not events:
        print('No events in DB. Run the pipeline on a video first.')
        return
    e = events[0]
    eid, ts, label, score, bbox_s, frame_path, clip_path, meta = e
    try:
        bbox = ast.literal_eval(bbox_s)
    except Exception:
        bbox = []
    # bbox expected [x1,y1,x2,y2] or similar
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        x1, y1, x2, y2 = map(int, bbox[:4])
    else:
        x1 = y1 = x2 = y2 = None

    try:
        meta_obj = ast.literal_eval(meta) if isinstance(meta, str) else (meta or {})
    except Exception:
        meta_obj = {}

    source = meta_obj.get('source')
    frame_index = meta_obj.get('frame_index')
    source_fps = float(meta_obj.get('source_fps') or 30.0)

    if not source or frame_index is None or not os.path.exists(source):
        # fallback to still-image replay if source metadata is not present
        if not frame_path or not os.path.exists(frame_path):
            print(f'Frame not found: {frame_path}')
            return
        img = cv2.imread(frame_path)
        if img is None:
            print('Unable to read frame image')
            return
        if x1 is not None:
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            rw = max(10, int((x2 - x1) / 2))
            rh = max(10, int((y2 - y1) / 2))
            radius = max(rw, rh)
            cv2.circle(img, (cx, cy), radius, (0, 0, 255), 4)
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(img, f'{label} {score:.2f}', (max(0, x1), max(0, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        outdir = os.path.join(CONFIG['storage']['frames_dir'], 'annotated')
        os.makedirs(outdir, exist_ok=True)
        outpath = os.path.join(outdir, f'event_{int(ts)}.jpg')
        cv2.imwrite(outpath, img)
        replay_path = outpath
        open_replay(replay_path)
        return
    else:
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            print(f'Could not open original source: {source}')
            return
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total_frames <= 0:
            print('Could not determine source frame count')
            cap.release()
            return

        # Build a hindsight reference from the event frame so we can keep marking
        # the same suspect as they move through the scene.
        suspect_seeds = []
        if frame_path and os.path.exists(frame_path):
            event_img = cv2.imread(frame_path)
            if event_img is not None:
                object_seed = find_orange_object_bbox(event_img)
                event_people = find_person_bboxes(event_img)
                if event_people:
                    if object_seed is not None:
                        ox1, oy1, ox2, oy2 = object_seed
                        ocx = (ox1 + ox2) / 2.0
                        ocy = (oy1 + oy2) / 2.0
                        suspect_seeds = sorted(
                            event_people,
                            key=lambda box: ((box[0] + box[2]) / 2.0 - ocx) ** 2 + ((box[1] + box[3]) / 2.0 - ocy) ** 2,
                        )[:2]
                    else:
                        suspect_seeds = event_people[:2]

        # Replay only a short event window with a little padding for context.
        # Increase pre-event padding to give more lead-in before the suspicious activity.
        window_before = int(source_fps * 5.0)
        window_after = int(source_fps * 2.0)
        start_frame = max(0, int(frame_index) - window_before)
        end_frame = min(total_frames - 1, int(frame_index) + window_after)

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        ok, sample = cap.read()
        if not ok or sample is None:
            print('Could not read frames from original source')
            cap.release()
            return
        out_h, out_w = sample.shape[:2]
        video_dir = os.path.join(CONFIG['storage']['clips_dir'], 'replay')
        os.makedirs(video_dir, exist_ok=True)
        replay_path = os.path.join(video_dir, f'event_{int(ts)}.mp4')
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(replay_path, fourcc, source_fps, (out_w, out_h))
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        current = start_frame
        tracked_suspects = suspect_seeds[:]
        devnull_out = open(os.devnull, 'w')
        devnull_err = open(os.devnull, 'w')
        try:
            with contextlib.redirect_stdout(devnull_out), contextlib.redirect_stderr(devnull_err):
                while current <= end_frame:
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        break

                    person_boxes = find_person_bboxes(frame)
                    frame_out = frame.copy()
                    next_tracked = []

                    for box in person_boxes:
                        iou = max((bbox_iou(box, seed) for seed in tracked_suspects), default=0.0)
                        if iou >= 0.20:
                            next_tracked.append(box)

                        x1, y1, x2, y2 = box
                        if iou >= 0.20:
                            cv2.rectangle(frame_out, (x1, y1), (x2, y2), (0, 0, 255), 4)
                        else:
                            cv2.rectangle(frame_out, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    if next_tracked:
                        tracked_suspects = next_tracked[:]

                    writer.write(frame_out)
                    current += 1
        finally:
            devnull_out.close()
            devnull_err.close()
        writer.release()
        cap.release()
        open_replay(replay_path)


if __name__ == '__main__':
    main()
