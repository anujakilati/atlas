import os
from pathlib import Path
import time
import subprocess
from typing import Optional

def ensure_dirs(cfg):
    Path(cfg["storage"]["frames_dir"]).mkdir(parents=True, exist_ok=True)
    Path(cfg["storage"]["clips_dir"]).mkdir(parents=True, exist_ok=True)

def save_frame(image, out_dir: str, prefix: str = "frame") -> str:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    path = Path(out_dir) / f"{prefix}_{ts}.jpg"
    # image assumed to be BGR numpy array
    import cv2
    cv2.imwrite(str(path), image)
    return str(path)

def save_clip(video_path: str, start_s: float, duration_s: float, out_dir: str, prefix: str = "clip") -> Optional[str]:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    name = f"{prefix}_{int(start_s)}_{int(duration_s)}.mp4"
    out_path = Path(out_dir) / name
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-ss", str(start_s), "-t", str(duration_s),
        "-c", "copy", str(out_path)
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(out_path)
    except Exception:
        return None
