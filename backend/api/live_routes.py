from fastapi import APIRouter, HTTPException

from backend.live.camera_worker import CameraWorker
from backend.live.frame_source import check_live_feed
from backend.live.monitor_service import get_monitor
from backend.live.supabase_store import SupabaseStore
from backend.utils.logger import get_logger
import os

router = APIRouter()
logger = get_logger("live_api")


@router.get("/live/status")
async def live_status():
    """Per-camera live feed status and last monitor results."""
    monitor = get_monitor()
    base = monitor.status()
    try:
        store = SupabaseStore()
        devices = store.list_all_devices()
        supabase_url = os.getenv("SUPABASE_URL", "")
        cameras = []
        for d in devices:
            live = check_live_feed(supabase_url, d["id"], d.get("status", "offline"))
            cameras.append(
                {
                    "device_id": d["id"],
                    "name": d.get("name"),
                    "placement": d.get("placement"),
                    "status": d.get("status"),
                    "feed_live": live.is_live,
                    "feed_reason": live.reason,
                }
            )
        base["cameras"] = cameras
    except Exception as e:
        base["error"] = str(e)
    return base


@router.post("/live/monitor/start")
async def start_monitor():
    monitor = get_monitor()
    await monitor.start()
    return {"status": "started", **monitor.status()}


@router.post("/live/monitor/stop")
async def stop_monitor():
    monitor = get_monitor()
    await monitor.stop()
    return {"status": "stopped"}


@router.post("/live/monitor/run-once")
async def run_monitor_once():
    monitor = get_monitor()
    results = await monitor.run_once()
    return {"results": results, "count": len(results)}


@router.post("/live/analyze/{device_id}")
async def analyze_device(device_id: str):
    """Analyze one camera's current live.webm chunk immediately."""
    try:
        store = SupabaseStore()
        devices = store.list_all_devices()
        device = next((d for d in devices if d["id"] == device_id), None)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        worker = CameraWorker(device, store=store)
        result = worker.process_once()
        return result or {"device_id": device_id, "analyzed": False}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("analyze_device failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
