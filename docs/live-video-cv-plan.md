# Live Video Computer Vision — Implementation Plan

## Problem

The current pipeline (`main.py` → `run()`) operates on pre-recorded video files. It uses `cv2.VideoCapture(VIDEO_PATH)` with a known frame count, looping via `% total`. Live streams have no frame count, so this model breaks.

Everything else — the rolling buffer, YOLO time-gating, session state machine, Nemotron async reasoning, Supabase writes — is already designed for real-time use. The gap is only the stream ingestion layer and reconnect handling.

---

## Target Architecture

```
[IP Camera / Webcam / Browser]
       │  RTSP / WebRTC
       ▼
[CV Worker Service]
  • cv2.VideoCapture("rtsp://..." or 0)
  • YOLO every ~70ms (already time-gated at YOLO_INTERVAL_SEC)
  • RollingBuffer keeps last 15s in RAM — nothing written to disk continuously
  • Suspicion score crosses threshold?
    → clip saved from RollingBuffer
    → Nemotron reasoning fires async
    → event inserted to Supabase DB
       │
       ▼
[atlas-app frontend]
  live alert push via Supabase realtime
```

---

## Why This is Efficient

The `RollingBuffer` (`pipeline/event_buffer/rolling_buffer.py`) holds the last N seconds of frames **in memory only**. Disk writes happen only when an incident is confirmed. This means:

- No continuous recording to disk
- YOLO runs at ~14fps, not every frame (already enforced by `YOLO_INTERVAL_SEC = 0.07`)
- Nemotron (expensive LLM call) only fires on threshold breach, already async
- CPU/GPU load is proportional to detection frequency, not stream framerate

---

## Stream Source Options

| Source | `VideoCapture` argument | Notes |
|---|---|---|
| Local webcam | `0` or `1` | Works today, no driver changes needed |
| IP camera (RTSP) | `"rtsp://user:pass@ip:554/stream"` | Most IP cameras support this natively |
| HLS/HTTP stream | `"http://host/stream.m3u8"` | OpenCV handles natively |
| Browser cam (WebRTC) | Needs a relay bridge | Most complex — see WebRTC section below |

---

## WebRTC Case (Browser Camera Source)

The atlas-app already has camera code (see `atlas-app/src/`). WebRTC frames cannot go directly into OpenCV. Three options, ordered by complexity:

1. **Re-stream relay (simplest)**: Browser → WebRTC → relay server (e.g., [`mediamtx`](https://github.com/bluenviron/mediamtx)) → RTSP → OpenCV. `mediamtx` is a single binary, Docker-friendly.
2. **`aiortc` in Python**: Receive WebRTC directly in the CV worker using the `aiortc` library. More control, no relay dependency.
3. **Device publishes RTSP directly**: If the camera device (not the browser) streams RTSP, the browser is only used for viewing and alert display. This is the cleanest separation.

---

## Changes Required in `main.py`

The `run()` function needs three targeted changes:

### 1. Accept a live source
```python
# Change this:
VIDEO_PATH = os.getenv("VIDEO_PATH", "videos/nishan-kidnap.MOV")

# To accept RTSP URLs or webcam index:
VIDEO_PATH = os.getenv("VIDEO_PATH", "0")  # 0 = default webcam
# Or: "rtsp://admin:password@192.168.1.100:554/stream1"
```

### 2. Remove the frame-looping logic
Lines 225–231 in `main.py` compute `target_frame = int(elapsed * fps) % total` — this is meaningless for live streams. Replace the wall-clock targeting block with a simple sequential read and drop frame-seeking entirely.

### 3. Add reconnect handling
Live streams drop. Wrap `cap.read()` with a reconnect loop:
```python
ret, frame = cap.read()
if not ret:
    cap.release()
    time.sleep(2)
    cap = cv2.VideoCapture(VIDEO_PATH)
    continue
```

No other changes needed — the rest of the pipeline is already stream-compatible.

---

## `backend/ingestion/ingester.py` Path

The `CCTVPipeline` in `backend/pipelines/pipeline.py` uses `VideoIngester`. If the async batch path is also needed for live streams, `VideoIngester` should similarly be updated to handle reconnect and treat a live source as an infinite iterator rather than a finite file.

---

## Deployment

### Local (dev)
Run the CV worker as a background process pointing at a local webcam:
```bash
VIDEO_PATH=0 python main.py
```

### Server / Docker
The `docker/` directory already exists. Package the CV worker as a container:
- Base image with Python + OpenCV + CUDA (if GPU available)
- Accept `VIDEO_PATH` as an env var (RTSP URL of network camera)
- Events write to Supabase — no direct connection to the frontend required
- The frontend receives live alerts via Supabase Realtime (already in use)

---

## Recommended Implementation Order

1. **Validate the live loop** — swap `VIDEO_PATH` to `0` (webcam), remove `% total` logic, confirm the rest of the pipeline runs without errors
2. **Add reconnect handling** — wrap `cap.read()` as described above
3. **Test with an RTSP source** — use a local IP camera or a test RTSP server (e.g., `mediamtx` serving a file as a stream)
4. **Wire alerts to Supabase** — ensure events from live sessions appear in the atlas-app frontend in real time
5. **Dockerize** — wrap the worker for server deployment

---

## Files Relevant to This Work

| File | Role |
|---|---|
| `main.py:188–386` | Main real-time loop — primary change target |
| `pipeline/event_buffer/rolling_buffer.py` | In-memory frame buffer — no changes needed |
| `pipeline/nemotron_reasoning/engine.py` | Async LLM reasoning — no changes needed |
| `backend/ingestion/ingester.py` | VideoIngester for async pipeline path |
| `backend/pipelines/pipeline.py` | CCTVPipeline (async batch path) |
| `backend/api/main.py` | FastAPI server — could expose a `/stream/start` endpoint |
| `docker/` | Deployment target for the CV worker |