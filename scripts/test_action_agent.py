#!/usr/bin/env python3
"""
Smoke-test for the OpenClaw → NemoClaw action pipeline.
Also streams the kidnapping video with YOLO to the AI Watch tab in the UI.

Run from the project root inside the venv:
    source .venv/bin/activate
    python scripts/test_action_agent.py

Set NEMOCLAW_ENABLED=0 to skip the NVIDIA API call and use rule-based dispatch only.
"""
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load .env so Supabase + NVIDIA creds are available
_env = ROOT / ".env"
if _env.exists():
    with open(_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

from pipeline.action_agent.dispatcher import ActionDispatcher, ActionSpec
from pipeline.action_agent.executor import NemoClawExecutor
from pipeline.nemotron_reasoning.engine import IncidentReport
from scripts.yolo_watch import stream_video

SB_URL = os.getenv("VITE_SUPABASE_URL", "")
SB_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
BUBBLE_ID = os.getenv("BUBBLE_ID", "")
DEVICE_ID = os.getenv("DEVICE_ID", "")

NEMOCLAW_ENABLED = os.getenv("NEMOCLAW_ENABLED", "1")

# ── Start YOLO stream in background (kidnapping video) ────────────────────────
_KIDNAP_VIDEO = str(ROOT / 'videos' / 'nishan-kidnap.MOV')
_yolo_thread = threading.Thread(
    target=stream_video,
    args=(_KIDNAP_VIDEO,),
    daemon=True,
)
_yolo_thread.start()
print('[YoloWatch] AI Watch tab will show the kidnapping video. Open it in the UI now.')
time.sleep(1)  # give the server a moment to bind

print(f"\n{'='*55}")
print("  Action Agent Smoke Test")
print(f"{'='*55}")
print(f"  Supabase URL  : {'SET' if SB_URL else 'NOT SET — Supabase steps will be skipped'}")
print(f"  Bubble ID     : {BUBBLE_ID or 'NOT SET'}")
print(f"  Device ID     : {DEVICE_ID or 'NOT SET'}")
print(f"  NEMOCLAW_ENABLED: {NEMOCLAW_ENABLED}")
print(f"  NVIDIA_API_KEY  : {'SET' if os.getenv('NVIDIA_API_KEY') else 'NOT SET — rule-based fallback will be used'}")
print(f"{'='*55}\n")


def make_report(incident_type: str, risk_level: str = "medium") -> IncidentReport:
    return IncidentReport(
        incident_id=f"test_{incident_type}_{int(time.time())}",
        incident_confirmed=True,
        incident_type=incident_type,
        confidence=0.85,
        objects_involved=["person"],
        person_behavior=f"Test: person exhibiting {incident_type.replace('_', ' ')} behavior",
        risk_level=risk_level,
        recommended_action="alert_operator",
        summary=f"[TEST] {incident_type.replace('_', ' ').title()} detected near front entrance.",
        notifications={
            "short": f"[TEST] {incident_type} alert",
            "medium": f"[TEST] {incident_type} detected",
            "long": f"[TEST] Full description of {incident_type} incident",
        },
        analyzed_at=time.time(),
        evidence_frame_count=3,
    )


def run_test(label: str, report: IncidentReport):
    print(f"── TEST: {label} ──────────────────────────────")
    executor = NemoClawExecutor(SB_URL, SB_KEY, BUBBLE_ID or None)
    dispatcher = ActionDispatcher()
    dispatcher.set_executor(executor)
    dispatcher.dispatch_async(report, device_id=DEVICE_ID or None, bubble_id=BUBBLE_ID or None)
    time.sleep(4)  # wait for background thread to finish
    dispatcher.stop()
    print()


# ── Test 1: loitering → should notify only
run_test(
    "loitering (expect: notify)",
    make_report("loitering", risk_level="low"),
)

# ── Test 2: suspicious_behavior → should lock_camera + notify
run_test(
    "suspicious_behavior (expect: lock_camera + notify)",
    make_report("suspicious_behavior", risk_level="medium"),
)

# ── Test 3: false_alarm → should no-op
run_test(
    "false_alarm (expect: no action)",
    make_report("false_alarm", risk_level="low"),
)

print("Done. Check Supabase device_events for guardian_action and camera_lock rows.")
