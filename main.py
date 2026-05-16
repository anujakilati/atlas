"""
Atlas AI Surveillance Pipeline
================================
Layer 1  Realtime loop   — YOLO + tracking + pixel-diff grid (every frame)
Layer 2  Session engine  — multi-object session, fires on first removal + on session end
Layer 3  Nemotron async  — reasons over full session context, never blocks video
"""

import time
import uuid
import os
import sys
import argparse
import asyncio
import subprocess
from pathlib import Path

import cv2
import numpy as np
from dotenv import load_dotenv

from pipeline.detection.yolo_detector import YOLODetector
from pipeline.tracking.person_tracker import PersonTracker
from pipeline.tracking.object_inventory import ObjectInventory
from pipeline.state_machine.session import InteractionSession, SessionState, ObjectEvent
from pipeline.roi_logic.zones import ProtectedZone
from pipeline.event_buffer.rolling_buffer import RollingBuffer
from pipeline.clip_generation.clip_builder import ClipBuilder
from pipeline.nemotron_reasoning.engine import NemotronEngine, IncidentPayload
from pipeline.notifications.alerts import generate as make_notifications
from pipeline.display.monitor import SurveillanceMonitor, DISPLAY_W, VIDEO_W, VIDEO_H
from backend.pipelines.pipeline import CCTVPipeline
from backend.reports.generator import generate_report, report_markdown
from backend.config import CONFIG
from backend.storage import db

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
# Default: honor `VIDEO_PATH` from environment if present, otherwise use bundle default
VIDEO_PATH = os.getenv("VIDEO_PATH", "videos/nishan-kidnap.MOV")
OUTPUT_DIR = Path("detection_results/pipeline")

# Protected zone in original 1920×1080 coords — covers the table area.
ROI = (380, 260, 1480, 860)

YOLO_INTERVAL_SEC = 0.07    # ~14 fps of inference
BUFFER_SEC        = 15.0
PRE_EVENT_SEC     = 10.0

# ── Init modules ──────────────────────────────────────────────────────────────
detector  = YOLODetector(conf=0.38)
tracker   = PersonTracker()
inventory = ObjectInventory()
zone      = ProtectedZone(*ROI)
nemotron  = NemotronEngine()
monitor   = SurveillanceMonitor()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Shared session state (modified by Nemotron callback) ──────────────────────
_session: InteractionSession | None = None
_last_report = None


def run_batch(video_path: str):
    """Run the batch analyzer, print a report, and generate the latest replay."""
    print(f"\n📦 Batch analysis: {video_path}")
    
    # Clear the database to ensure fresh analysis
    db_path = CONFIG['storage']['db_path']
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"✓ Cleared old database: {db_path}")
    
    # Clear old frames to force fresh capture
    frames_dir = CONFIG['storage']['frames_dir']
    if os.path.exists(frames_dir):
        import shutil
        shutil.rmtree(frames_dir)
        print(f"✓ Cleared old frames: {frames_dir}")
    
    # Clear old replay files to force fresh generation
    replay_dir = CONFIG['storage'].get('clips_dir', './storage/clips')
    if replay_dir:
        replay_dir = os.path.join(replay_dir, 'replay')
        if os.path.exists(replay_dir):
            import shutil
            shutil.rmtree(replay_dir)
            print(f"✓ Cleared old replays: {replay_dir}")
    
    # Initialize fresh database
    db.init_db(db_path)
    print(f"✓ Initialized fresh database")
    
    # Run pipeline on the selected video
    print(f"→ Analyzing {video_path}...")
    asyncio.run(CCTVPipeline(video_path).run())

    # Generate and show report
    report = generate_report(limit=50)
    events = report.get('timeline', [])
    print(f"\n✓ Analysis complete. Found {len(events)} event(s)")
    if events:
        print("\n" + report_markdown(report))
        
        # Generate replay for the latest event matching this video
        print(f"\n→ Generating replay for {video_path}...")
        replay_script = Path("scripts/show_latest_event.py")
        if replay_script.exists():
            result = subprocess.run([
                sys.executable,
                str(replay_script),
                "--source",
                video_path,
            ], check=False)
            if result.returncode == 0:
                print(f"✓ Replay generated successfully")
        else:
            print(f"Replay script not found: {replay_script}")
    else:
        print("❌ No suspicious activity detected in this video.")


def on_nemotron_result(report):
    global _last_report
    _last_report = report
    monitor.set_incident(report)
    notifs = make_notifications(report)
    print(f"\n{'='*62}")
    print(f"  NEMOTRON  [{report.incident_id}]")
    print(f"  confirmed : {report.incident_confirmed}")
    print(f"  type      : {report.incident_type}")
    print(f"  risk      : {report.risk_level}   confidence: {report.confidence:.0%}")
    print(f"  action    : {report.recommended_action}")
    print(f"  summary   : {report.summary}")
    print(f"  PUSH      : {notifs['short']}")
    print(f"{'='*62}\n")


def _fire_nemotron(session: InteractionSession, buffer: RollingBuffer,
                   builder: ClipBuilder, video_ts: float,
                   roi_change: float, is_final: bool):
    """Build evidence payload and send to Nemotron asynchronously."""
    window    = buffer.get_window(PRE_EVENT_SEC, 0.0, video_ts)
    keyframes = builder.select_keyframes(window, [])
    if not keyframes:
        return

    clip_path = builder.build_evidence_clip(window, session.session_id)
    montage   = builder.build_montage(keyframes, session.session_id)
    b64s      = builder.frames_to_b64(keyframes)

    label = "FINAL" if is_final else "PARTIAL"
    print(f"\n🔴 Nemotron [{label}] session={session.session_id}"
          f"  objects_removed={inventory.removed_count()}"
          f"  roi_change={roi_change:.1%}")
    if montage:
        print(f"   montage → {montage}")

    payload = IncidentPayload(
        incident_id=f"{session.session_id}_{session.nemotron_calls}",
        suspicion_score=session.peak_suspicion,
        timeline=[
            {"frame": b.frame_num, "ts": round(b.video_ts, 2),
             "suspicion": round(b.suspicion, 3)}
            for b in window[::max(1, len(window)//8)]
        ],
        state_transitions=session.to_dict()["transitions"],
        evidence_b64=b64s,
        roi_metadata={
            "coords": ROI,
            "label": "table_zone",
            "roi_change_pct": round(roi_change, 4),
            "baseline_ready": inventory.ready,
            "objects_present_at_start": inventory.present_labels(),
            "objects_removed": inventory.removed_labels(),
            "is_final_report": is_final,
        },
        tracker_summary=session.to_dict(),
        clip_path=str(clip_path) if clip_path else None,
    )
    monitor.set_analyzing(True)
    nemotron.analyze_async(payload, on_nemotron_result)
    session.mark_escalated()


# ── Main loop ─────────────────────────────────────────────────────────────────
def run():
    global _session

    cap = cv2.VideoCapture(VIDEO_PATH)
    if not cap.isOpened():
        print(f"❌ Cannot open {VIDEO_PATH}"); return

    fps     = cap.get(cv2.CAP_PROP_FPS)
    total   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    orig_w  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    orig_h  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    print(f"🎬 {orig_w}×{orig_h} @ {fps:.0f} FPS — {total} frames ({total/fps:.1f}s)")
    print(f"🛡  ROI: {ROI}   Grid: {inventory.GRID_ROWS}×{inventory.GRID_COLS} cells")
    print(f"📺 Display: {DISPLAY_W}×{VIDEO_H}   Q=quit  Space=pause\n")

    buffer  = RollingBuffer(fps, BUFFER_SEC)
    builder = ClipBuilder(OUTPUT_DIR, fps)

    play_start = time.monotonic()
    pause_debt = 0.0
    pause_at   = None
    paused     = False

    last_yolo_t  = 0.0
    detections   = []
    tracks       = []
    frame_num    = 0
    roi_change   = 0.0
    suspicion    = 0.0
    vis          = np.zeros((orig_h, orig_w, 3), dtype=np.uint8)
    session_state = SessionState.IDLE

    while True:
        if not paused:
            # ── Wall-clock frame targeting ─────────────────────────────────
            elapsed      = time.monotonic() - play_start - pause_debt
            target_frame = int(elapsed * fps) % total
            cur_pos      = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

            if target_frame - cur_pos > 1:
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            elif target_frame < cur_pos - 5:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

            ret, frame = cap.read()
            if not ret:
                play_start = time.monotonic(); pause_debt = 0.0
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            frame_num = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
            video_ts  = frame_num / fps
            vis       = frame

            # ── YOLO (time-gated) ──────────────────────────────────────────
            now_mono = time.monotonic()
            if now_mono - last_yolo_t >= YOLO_INTERVAL_SEC:
                detections  = detector.detect(frame)
                tracks      = tracker.update(detections, frame_num)
                last_yolo_t = now_mono

            # ── ROI update ─────────────────────────────────────────────────
            entered, exited, in_roi_ids, approaching_ids = zone.update(tracks, frame)

            # ── Object inventory ───────────────────────────────────────────
            now_mono = time.monotonic()

            if _session is None:
                # Try to build baseline while zone is clear
                inventory.try_catalog(frame, zone, detections, in_roi_ids, frame_num)

            # Always compute ROI diff for display
            if zone.has_baseline() and not in_roi_ids:
                roi_change = zone.roi_change_score(frame)
            else:
                roi_change = 0.0

            # Detect object removals mid-session
            newly_removed = []
            if _session is not None and inventory.ready:
                newly_removed = inventory.update(frame, zone, frame_num, video_ts)
                for obj in newly_removed:
                    ev = ObjectEvent(
                        obj_id=obj.obj_id, label=obj.label,
                        event_type="removed", frame_num=frame_num,
                        video_ts=video_ts, confidence=obj.confidence,
                        cell=obj.cell,
                    )
                    _session.record_object_event(ev)
                    print(f"  📦 Object removed: {obj.label}  cell={obj.cell}"
                          f"  t={video_ts:.1f}s  conf={obj.confidence:.0%}")

            # ── Suspicion score (lightweight) ──────────────────────────────
            suspicion = 0.0
            if in_roi_ids:
                suspicion += 0.20
            if _session and _session.state in (SessionState.ACTIVE,
                                               SessionState.OBJECT_EVENT):
                dwell = now_mono - (_session.last_activity_ts - 0.001)
                suspicion += min(0.25, 0.25 * dwell / 12.0)
            suspicion += min(0.40, inventory.removed_count() * 0.40)
            suspicion += min(0.30, roi_change * 5.0)
            suspicion = min(suspicion, 1.0)

            # ── Session lifecycle ──────────────────────────────────────────
            if _session is None:
                if in_roi_ids or approaching_ids:
                    _session = InteractionSession(frame_num, video_ts)
                    print(f"\n🟡 Session started [{_session.session_id}]  t={video_ts:.1f}s")

            if _session is not None:
                _session.update(
                    frame_num=frame_num,
                    in_roi_ids=in_roi_ids,
                    approaching_ids=approaching_ids,
                    suspicion=suspicion,
                    now_mono=now_mono,
                )
                session_state = _session.state

                # Partial escalation — fire on first (and each subsequent) removal
                if _session.should_escalate_partial():
                    _fire_nemotron(_session, buffer, builder, video_ts,
                                   roi_change, is_final=False)

                # Final escalation — full session report on timeout
                if _session.should_escalate_final():
                    _fire_nemotron(_session, buffer, builder, video_ts,
                                   roi_change, is_final=True)
                    print(f"✅ Session complete [{_session.session_id}]"
                          f"  events={len(_session.object_events)}\n")
                    _session = None
                    inventory.reset()
                    session_state = SessionState.IDLE
            else:
                session_state = SessionState.IDLE

            # ── Rolling buffer ─────────────────────────────────────────────
            buffer.push(frame, frame_num, video_ts, suspicion)

        # ── Render ────────────────────────────────────────────────────────
        dwell = (_session.last_activity_ts - time.monotonic() + 0.001
                 if _session else 0.0)

        # Annotate removed-object cells on video
        if inventory.ready:
            roi_img_h = zone.y2 - zone.y1
            roi_img_w = zone.x2 - zone.x1
            rh = roi_img_h // inventory.GRID_ROWS
            cw = roi_img_w // inventory.GRID_COLS
            for obj in inventory.objects.values():
                if obj.status == "REMOVED":
                    r, c = obj.cell
                    x1 = zone.x1 + c * cw
                    y1 = zone.y1 + r * rh
                    x2, y2 = x1 + cw, y1 + rh
                    cv2.rectangle(vis, (x1,y1), (x2,y2), (0,0,200), 2)
                    cv2.putText(vis, f"REMOVED:{obj.label}", (x1+4, y1+18),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,0,220), 1)
                elif obj.confidence > 0.2:
                    r, c = obj.cell
                    x1 = zone.x1 + c * cw
                    y1 = zone.y1 + r * rh
                    x2, y2 = x1 + cw, y1 + rh
                    cv2.rectangle(vis, (x1,y1), (x2,y2), (0,100,255), 1)

        display = monitor.render(
            frame=vis, tracks=tracks, zone=zone,
            state=session_state, suspicion=suspicion,
            dwell=abs(dwell), roi_change=roi_change,
            frame_num=frame_num, fps=fps,
        )

        # Session info overlay on telemetry panel (bottom strip)
        if _session:
            info = (f"session:{_session.session_id}"
                    f"  events:{len(_session.object_events)}"
                    f"  removed:{inventory.removed_count()}")
            cv2.putText(display, info, (VIDEO_W + 14, VIDEO_H - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36, (100,100,100), 1)

        cv2.imshow("Atlas — AI Surveillance  (Q=quit  Space=pause)", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord(" "):
            paused = not paused
            if paused:
                pause_at = time.monotonic()
            else:
                pause_debt += time.monotonic() - pause_at
                pause_at = None

    cap.release()
    cv2.destroyAllWindows()
    nemotron.stop()
    print("✓ Pipeline closed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Atlas AI surveillance on a video file")
    parser.add_argument("-v", "--video", help="Path to input video file to analyze")
    parser.add_argument("--batch", action="store_true",
                        help="Run the batch analyzer, print a report, and generate replay")
    parser.add_argument("--dry-run", action="store_true", help="Print chosen video and exit without running")
    args = parser.parse_args()

    # Resolve video selection: CLI arg > ENV var > module default
    if args.video:
        VIDEO_PATH = args.video
    else:
        VIDEO_PATH = os.getenv("VIDEO_PATH", VIDEO_PATH)

    print(f"Using video: {VIDEO_PATH}")
    if args.dry_run:
        sys.exit(0)

    if args.batch:
        run_batch(VIDEO_PATH)
        sys.exit(0)

    run()
