"""Poll all online cameras and run live suspicious-activity analysis."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from backend.live.camera_worker import CameraWorker
from backend.live.frame_source import check_live_feed
from backend.live.supabase_store import SupabaseStore
from backend.utils.logger import get_logger

logger = get_logger("monitor_service")


class LiveMonitorService:
    def __init__(self, poll_interval_sec: float = 12.0):
        self.poll_interval = poll_interval_sec
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_results: list[dict[str, Any]] = []
        self._last_run_at: float | None = None
        self._workers: dict[str, CameraWorker] = {}

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self):
        while self._running:
            try:
                await self.run_once()
            except Exception as e:
                logger.exception("monitor cycle failed: %s", e)
            await asyncio.sleep(self.poll_interval)

    async def run_once(self) -> list[dict[str, Any]]:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, self._run_sync)
        self._last_results = results
        self._last_run_at = time.time()
        return results

    def _run_sync(self) -> list[dict[str, Any]]:
        import os

        store = SupabaseStore()
        devices = store.list_all_devices()
        supabase_url = os.getenv("SUPABASE_URL", "")
        results: list[dict[str, Any]] = []

        for device in devices:
            device_id = device["id"]
            live = check_live_feed(supabase_url, device_id, device.get("status", "offline"))
            if not live.is_live:
                skipped = {
                    "device_id": device_id,
                    "name": device.get("name"),
                    "status": device.get("status"),
                    "live": False,
                    "reason": live.reason,
                }
                results.append(skipped)
                self._log_camera_result(skipped)
                continue

            worker = self._worker_for(device, store)
            try:
                result = worker.process_once()
                if result:
                    result["name"] = device.get("name")
                    results.append(result)
                    self._log_camera_result(result)
            except Exception as e:
                logger.exception("worker failed for %s: %s", device_id, e)
                results.append(
                    {"device_id": device_id, "name": device.get("name"), "live": True, "error": str(e)}
                )

        if not results:
            logger.info("monitor cycle: no devices in database")
        return results

    def _worker_for(self, device: dict, store: SupabaseStore) -> CameraWorker:
        device_id = device["id"]
        worker = self._workers.get(device_id)
        if worker is None:
            worker = CameraWorker(device, store=store)
            self._workers[device_id] = worker
        else:
            worker.device = device
        return worker

    @staticmethod
    def _log_camera_result(result: dict[str, Any]) -> None:
        name = result.get("name") or result.get("device_id", "?")
        if not result.get("live"):
            logger.info("%s: not live (%s)", name, result.get("reason", "?"))
            return
        if not result.get("analyzed"):
            logger.info("%s: live but %s", name, result.get("reason", "skipped"))
            return
        peak = result.get("peak_suspicion")
        if result.get("suspicious"):
            if result.get("skipped"):
                logger.info("%s: suspicious (cooldown) peak=%s", name, peak)
            else:
                logger.info(
                    "%s: INCIDENT peak=%s id=%s",
                    name,
                    peak,
                    result.get("incident_id", "?"),
                )
            return
        logger.info(
            "%s: ok peak=%s persons=%s motion=%s",
            name,
            peak,
            (result.get("yolo") or {}).get("person_count")
            if isinstance(result.get("yolo"), dict)
            else "?",
            (result.get("yolo") or {}).get("motion")
            if isinstance(result.get("yolo"), dict)
            else "?",
        )

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "last_run_at": self._last_run_at,
            "poll_interval_sec": self.poll_interval,
            "cameras": self._last_results,
        }


_monitor: LiveMonitorService | None = None


def get_monitor() -> LiveMonitorService:
    global _monitor
    if _monitor is None:
        _monitor = LiveMonitorService()
    return _monitor
