"""Supabase REST helpers for devices and camera activities."""

from __future__ import annotations

from typing import Any

import requests

from backend.env import get_supabase_key, get_supabase_url
from backend.utils.logger import get_logger

logger = get_logger("supabase_store")

BUCKET = "camera-feeds"


class SupabaseStore:
    def __init__(self):
        self.url = get_supabase_url()
        self.key = get_supabase_key()
        if not self.url or not self.key:
            raise RuntimeError(
                "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env "
                "(or VITE_SUPABASE_URL + SUPABASE_SERVICE_KEY / VITE_SUPABASE_ANON_KEY)."
            )

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def list_online_devices(self) -> list[dict[str, Any]]:
        r = requests.get(
            f"{self.url}/rest/v1/devices",
            headers=self._headers(),
            params={"select": "id,bubble,name,placement,status", "status": "eq.online"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def list_all_devices(self) -> list[dict[str, Any]]:
        r = requests.get(
            f"{self.url}/rest/v1/devices",
            headers=self._headers(),
            params={"select": "id,bubble,name,placement,status"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def insert_recording(
        self,
        device_id: str,
        storage_path: str,
        duration_ms: int | None = None,
    ) -> str | None:
        payload: dict[str, Any] = {
            "device": device_id,
            "storage_path": storage_path,
        }
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        r = requests.post(
            f"{self.url}/rest/v1/device_recordings",
            headers=self._headers(),
            json=payload,
            timeout=15,
        )
        if r.status_code >= 400:
            logger.warning("insert_recording failed: %s %s", r.status_code, r.text)
            return None
        data = r.json()
        row = data[0] if isinstance(data, list) and data else data
        return row.get("id") if isinstance(row, dict) else None

    def insert_device_event(self, row: dict[str, Any]) -> dict[str, Any]:
        r = requests.post(
            f"{self.url}/rest/v1/device_events",
            headers=self._headers(),
            json=row,
            timeout=15,
        )
        if r.status_code >= 400:
            logger.error("insert_device_event failed: %s %s", r.status_code, r.text)
            if r.status_code == 404 or "device_events" in (r.text or ""):
                raise RuntimeError(
                    "Table public.device_events is missing or not exposed. "
                    "Run atlas-app/supabase/device_events.sql in Supabase → SQL Editor, then restart the monitor."
                ) from None
            r.raise_for_status()
        data = r.json()
        return data[0] if isinstance(data, list) and data else data

    def insert_activity(self, row: dict[str, Any]) -> dict[str, Any]:
        """Legacy alias — maps camera_activities shape to device_events."""
        meta = row.get("nemotron_report") or {}
        if isinstance(meta, dict):
            meta = {
                **meta,
                "title": row.get("title"),
                "summary": row.get("summary"),
                "suspicion_score": row.get("suspicion_score"),
                "clip_storage_path": row.get("clip_storage_path"),
                "source": "live_monitor",
            }
        return self.insert_device_event(
            {
                "bubble": row["bubble"],
                "device": row["device"],
                "recording_id": row.get("recording_id"),
                "event_type": row.get("incident_type", "suspicious_behavior"),
                "event_subtype": "live_monitor",
                "risk_level": row.get("risk_level", "medium"),
                "confidence": float(row.get("suspicion_score", 0)),
                "incident_confirmed": bool(meta.get("incident_confirmed", False)),
                "metadata": meta,
            }
        )

    def upload_clip(self, storage_path: str, file_path: str, content_type: str = "video/mp4") -> str:
        with open(file_path, "rb") as f:
            body = f.read()
        r = requests.post(
            f"{self.url}/storage/v1/object/{BUCKET}/{storage_path}",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            data=body,
            timeout=120,
        )
        if r.status_code >= 400:
            logger.error("upload_clip failed: %s %s", r.status_code, r.text)
            r.raise_for_status()
        return f"{self.url}/storage/v1/object/public/{BUCKET}/{storage_path}"
