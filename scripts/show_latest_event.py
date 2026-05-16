#!/usr/bin/env python3
"""Load latest event, annotate the original video around the suspicious frame,
save the replay clip, open it, and print a short report."""
import ast
import base64
import contextlib
import json
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path so `backend` package imports work when
# running the script directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load environment variables from the root .env file if present.
_env_path = ROOT / '.env'
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _, _v = _line.partition('=')
                os.environ.setdefault(_k.strip(), _v.strip())

from backend.storage import db
from backend.config import CONFIG
from backend.utils.logger import get_logger
import cv2
import numpy as np

logger = get_logger('show_event')

CHARACTER_PROFILE_PROMPT = """\
You are a security analyst generating a suspect description from surveillance footage.
Only describe what is clearly visible in the image. Do not guess or infer details you cannot see.
Use "not visible" for any field you cannot determine with confidence.
Respond with ONLY valid JSON — no markdown, no extra text:

{
  "clothing": {
    "top": "color and type of upper body clothing, or 'not visible'",
    "bottom": "color and type of lower body clothing, or 'not visible'",
    "shoes": "footwear description, or 'not visible'",
    "accessories": "any clearly visible hats, bags, glasses, etc., or 'none visible'"
  },
  "physical": {
    "hair_color": "observed hair color, or 'not visible'",
    "hair_style": "length and style, or 'not visible'",
    "approximate_age": "estimated age range if determinable, or 'unknown'",
    "build": "slim|medium|stocky|athletic, or 'unknown'",
    "skin_tone": "observed skin tone, or 'not visible'"
  },
  "distinguishing_features": "only clearly visible tattoos, scars, or notable items — omit if none are apparent",
  "summary": "one-sentence description limited to only what is clearly visible in the image"
}"""


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


def find_person_detections(frame):
    """Return all person detections as ((x1,y1,x2,y2), confidence) tuples."""
    try:
        from backend.detectors.yolo_detector import YoloDetector
    except Exception:
        return []

    detector = find_person_detections._detector if hasattr(find_person_detections, "_detector") else None
    if detector is None:
        detector = YoloDetector('yolov8n.pt', device='cpu')
        find_person_detections._detector = detector

    with contextlib.redirect_stdout(open(os.devnull, 'w')), contextlib.redirect_stderr(open(os.devnull, 'w')):
        detections = detector.predict(frame, conf=0.25)
    results = []
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
        conf = float(det.get('score', 0.0))
        results.append(((x1, y1, x2, y2), conf))
    return results


def compute_clarity_score(frame, bbox, conf):
    """Score a detected person crop for suitability as a profile image (0.0–1.0)."""
    x1, y1, x2, y2 = bbox
    h, w = frame.shape[:2]

    if conf < 0.60:
        return 0.0
    crop = frame[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if laplacian_var < 50:
        return 0.0

    conf_score = conf

    bbox_area = max(0, x2 - x1) * max(0, y2 - y1)
    area_score = min(bbox_area / (w * h), 1.0)

    bbox_cx = (x1 + x2) / 2.0
    bbox_cy = (y1 + y2) / 2.0
    frame_cx = w / 2.0
    frame_cy = h / 2.0
    max_dist = (frame_cx ** 2 + frame_cy ** 2) ** 0.5
    dist = ((bbox_cx - frame_cx) ** 2 + (bbox_cy - frame_cy) ** 2) ** 0.5
    centrality_score = 1.0 - min(dist / max_dist, 1.0)

    sharpness_score = min(laplacian_var / 500.0, 1.0)

    return (
        0.30 * conf_score +
        0.40 * area_score +
        0.20 * centrality_score +
        0.10 * sharpness_score
    )


def crop_person(frame, bbox, padding=0.05):
    """Crop a person bounding box with proportional padding, clamped to frame bounds."""
    x1, y1, x2, y2 = bbox
    h, w = frame.shape[:2]
    bw = x2 - x1
    bh = y2 - y1
    pad_x = int(bw * padding)
    pad_y = int(bh * padding)
    cx1 = max(0, x1 - pad_x)
    cy1 = max(0, y1 - pad_y)
    cx2 = min(w, x2 + pad_x)
    cy2 = min(h, y2 + pad_y)
    return frame[cy1:cy2, cx1:cx2]


def frame_to_base64(frame):
    """Encode a BGR numpy frame as a base64 JPEG string."""
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("Failed to encode frame as JPEG")
    return base64.b64encode(buf.tobytes()).decode('utf-8')


def analyze_suspect(cropped_frame):
    """Send a cropped suspect image to Nemotron and return a character profile dict."""
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        logger.warning("NVIDIA_API_KEY not set — skipping character profile analysis")
        return {}

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not available — skipping character profile analysis")
        return {}

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key,
    )

    b64 = frame_to_base64(cropped_frame)
    content = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        },
        {"type": "text", "text": CHARACTER_PROFILE_PROMPT},
    ]

    try:
        resp = client.chat.completions.create(
            model="nvidia/nemotron-nano-12b-v2-vl",
            messages=[{"role": "user", "content": content}],
            temperature=0.1,
            max_tokens=600,
        )
        raw = resp.choices[0].message.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Character profile JSON parse error: %s", e)
        return {}
    except Exception as e:
        logger.warning("Character profile analysis failed: %s", e)
        return {}


def print_character_profile(profile, event_id):
    """Pretty-print the character profile to stdout."""
    sep = "=" * 60
    if not profile:
        print(f"\n{sep}")
        print(f"  CHARACTER PROFILE — Event {event_id}")
        print(sep)
        print("  Analysis unavailable.")
        print(sep)
        return

    print(f"\n{sep}")
    print(f"  CHARACTER PROFILE — Event {event_id}")
    print(sep)

    clothing = profile.get("clothing", {})
    if clothing:
        print("\nCLOTHING")
        for key, val in clothing.items():
            print(f"  {key.capitalize():12s}: {val}")

    physical = profile.get("physical", {})
    if physical:
        print("\nPHYSICAL DESCRIPTION")
        for key, val in physical.items():
            label = key.replace("_", " ").capitalize()
            print(f"  {label:20s}: {val}")

    features = profile.get("distinguishing_features")
    if features:
        print(f"\nDISTINGUISHING FEATURES\n  {features}")

    summary = profile.get("summary")
    if summary:
        print(f"\nSUMMARY\n  {summary}")

    print(sep)


def upload_crop_to_storage(cropped_frame, event_ts):
    """Upload a cropped suspect image to Supabase Storage and return its public URL."""
    import requests as req
    url = os.environ.get("VITE_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None

    ok, buf = cv2.imencode('.jpg', cropped_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        logger.warning("Failed to encode crop for upload")
        return None

    bucket = "profiles"
    filename = f"event_{int(event_ts)}_profile.jpg"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "image/jpeg",
    }

    # Create the bucket if it doesn't exist yet (idempotent — ignores 409 conflict).
    try:
        req.post(
            f"{url}/storage/v1/bucket",
            headers={**headers, "Content-Type": "application/json"},
            json={"id": bucket, "name": bucket, "public": True},
            timeout=10,
        )
    except Exception:
        pass

    # Upload the image (upsert so re-runs overwrite cleanly).
    try:
        resp = req.post(
            f"{url}/storage/v1/object/{bucket}/{filename}",
            headers={**headers, "x-upsert": "true"},
            data=buf.tobytes(),
            timeout=15,
        )
        resp.raise_for_status()
        public_url = f"{url}/storage/v1/object/public/{bucket}/{filename}"
        print(f"[Storage] Crop uploaded: {public_url}")
        return public_url
    except Exception as e:
        logger.warning("Failed to upload crop to Supabase Storage: %s", e)
        return None


def _supabase_headers(key):
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _jaccard_similarity(a, b):
    if not a or not b:
        return 0.0
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    intersection = len(sa & sb)
    union = len(sa | sb)
    return intersection / union if union > 0 else 0.0


def _histogram_similarity(img_a, img_b):
    """Compare two BGR images via per-channel histogram correlation (0–1)."""
    scores = []
    for ch in range(3):
        ha = cv2.calcHist([img_a], [ch], None, [64], [0, 256])
        hb = cv2.calcHist([img_b], [ch], None, [64], [0, 256])
        cv2.normalize(ha, ha)
        cv2.normalize(hb, hb)
        scores.append(max(0.0, cv2.compareHist(ha, hb, cv2.HISTCMP_CORREL)))
    return sum(scores) / len(scores)


def _download_image(url):
    """Download an image from a URL and return a BGR numpy array, or None."""
    import requests as req
    try:
        resp = req.get(url, timeout=10)
        resp.raise_for_status()
        arr = np.frombuffer(resp.content, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        return None


def is_duplicate_character(new_profile, new_crop, sb_url, key, threshold=0.80):
    """Return True if a sufficiently similar character already exists in the DB."""
    import requests as req
    new_summary = (new_profile.get("summary", "") if new_profile else "").lower()

    try:
        resp = req.get(
            f"{sb_url}/rest/v1/characters?select=id,sus_character_description,profile_crop_url&limit=50",
            headers=_supabase_headers(key),
            timeout=10,
        )
        resp.raise_for_status()
        existing = resp.json()
    except Exception as e:
        logger.warning("Could not fetch existing characters for dedup check: %s", e)
        return False

    for char in existing:
        existing_summary = (char.get("sus_character_description") or "").lower()
        text_sim = _jaccard_similarity(new_summary, existing_summary)

        img_sim = 0.0
        existing_url = char.get("profile_crop_url")
        if existing_url and new_crop is not None:
            remote = _download_image(existing_url)
            if remote is not None:
                img_sim = _histogram_similarity(new_crop, remote)

        # Weight: 50% text, 50% image (fall back to text-only if no image)
        if existing_url and new_crop is not None:
            similarity = 0.5 * text_sim + 0.5 * img_sim
        else:
            similarity = text_sim

        if similarity >= threshold:
            print(f"[Dedup] Matches existing character {char['id']} (similarity {similarity:.0%}) — skipping insert.")
            return True

    return False


def push_to_supabase(profile, event_meta, replay_path, crop_url=None, score=0.0, cropped_frame=None):
    """Insert a device_event + character record into Supabase."""
    import requests as req
    sb_url = os.environ.get("VITE_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not sb_url or not key:
        logger.warning("VITE_SUPABASE_URL or SUPABASE_SERVICE_KEY not set — skipping Supabase push")
        return

    headers = _supabase_headers(key)
    return_headers = {**headers, "Prefer": "return=representation"}

    # 1. Resolve bubble ID — use env override or fetch first bubble from Supabase
    bubble_id = os.environ.get("BUBBLE_ID")
    if not bubble_id:
        try:
            r = req.get(f"{sb_url}/rest/v1/bubbles?select=id&limit=1", headers=headers, timeout=10)
            r.raise_for_status()
            rows = r.json()
            bubble_id = rows[0]["id"] if rows else None
            if not bubble_id:
                print(f"[Supabase] bubble table returned no rows — check RLS or table name")
        except Exception as e:
            print(f"[Supabase] Could not fetch bubble ID: {e}")

    if not bubble_id:
        print("[Supabase] Skipping device_events insert — no bubble ID available")
    else:
        event_row = {
            "bubble": bubble_id,
            "event_type": "suspicious_person",
            "event_subtype": event_meta.get("label", "character_profile_generated"),
            "risk_level": "high" if score >= 0.8 else "medium" if score >= 0.5 else "low",
            "confidence": round(float(score), 4),
            "incident_confirmed": True,
            "metadata": {
                "source": event_meta.get("source"),
                "replay_path": replay_path,
                "profile_crop_url": crop_url,
                "character_profile": profile or {},
            },
        }
        try:
            resp = req.post(f"{sb_url}/rest/v1/device_events", headers=return_headers, json=event_row, timeout=10)
            resp.raise_for_status()
            print("[Supabase] device_events row inserted.")
        except Exception as e:
            print(f"[Supabase] Failed to insert device_event: {e} — response: {getattr(e, 'response', None) and e.response.text}")

    # 2. Deduplicate then insert character
    if is_duplicate_character(profile, cropped_frame, sb_url, key):
        return

    summary = profile.get("summary", "") if profile else ""
    character_row = {
        "sus_character_description": summary,
        "profile_crop_url": crop_url,
    }
    try:
        resp = req.post(f"{sb_url}/rest/v1/characters", headers=return_headers, json=character_row, timeout=10)
        resp.raise_for_status()
        character_id = resp.json()[0]["id"]
        print(f"[Supabase] Character {character_id} inserted.")
    except Exception as e:
        print(f"[Supabase] Failed to insert character: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Generate a replay for the latest matching event')
    parser.add_argument('--source', help='Only use events whose metadata source matches this video path')
    args = parser.parse_args()

    dpath = CONFIG['storage']['db_path']
    events = db.list_events(dpath, limit=500)
    if args.source:
        filtered = []
        for event in events:
            try:
                meta_obj = ast.literal_eval(event[7]) if isinstance(event[7], str) else (event[7] or {})
            except Exception:
                meta_obj = {}
            if meta_obj.get('source') == args.source:
                filtered.append(event)
        events = filtered
    if not events:
        if args.source:
            print(f'No events in DB for source: {args.source}')
        else:
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
        best_clarity = {"score": 0.0, "frame": None, "bbox": None}
        devnull_out = open(os.devnull, 'w')
        devnull_err = open(os.devnull, 'w')
        try:
            with contextlib.redirect_stdout(devnull_out), contextlib.redirect_stderr(devnull_err):
                while current <= end_frame:
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        break

                    detections = find_person_detections(frame)
                    frame_out = frame.copy()
                    next_tracked = []

                    seeding_failed = not tracked_suspects

                    for (box, conf) in detections:
                        iou = max((bbox_iou(box, seed) for seed in tracked_suspects), default=0.0)
                        is_suspect = iou >= 0.20 or seeding_failed

                        if is_suspect:
                            next_tracked.append(box)
                            clarity = compute_clarity_score(frame, box, conf)
                            if clarity > best_clarity["score"]:
                                best_clarity["score"] = clarity
                                best_clarity["frame"] = frame.copy()
                                best_clarity["bbox"] = box

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

        # --- Character profile generation ---
        if best_clarity["frame"] is not None:
            print(f"\n[Character Profile] Best clarity score: {best_clarity['score']:.3f}")
            cropped = crop_person(best_clarity["frame"], best_clarity["bbox"])
            profile = analyze_suspect(cropped)
            print_character_profile(profile, int(ts))

            profiles_dir = os.path.join(CONFIG['storage']['frames_dir'], 'profiles')
            os.makedirs(profiles_dir, exist_ok=True)
            profile_img_path = os.path.join(profiles_dir, f'event_{int(ts)}_profile.jpg')
            cv2.imwrite(profile_img_path, cropped)
            print(f"[Character Profile] Crop saved to: {profile_img_path}")

            crop_url = upload_crop_to_storage(cropped, ts)
            push_to_supabase(profile, meta_obj, replay_path, crop_url=crop_url, score=score, cropped_frame=cropped)
        else:
            print("\n[Character Profile] No clear suspect frame found during replay.")

        open_replay(replay_path)

    # Clean up raw suspicious frames — keep only profile crops in profiles/
    frames_dir = Path(CONFIG['storage']['frames_dir'])
    removed = 0
    for f in frames_dir.glob("susp_*.jpg"):
        try:
            f.unlink()
            removed += 1
        except Exception:
            pass
    if removed:
        print(f"[Cleanup] Removed {removed} raw frame(s) from {frames_dir}")


if __name__ == '__main__':
    main()
