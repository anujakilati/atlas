"""
NemoClaw — Action Executor
Receives an ActionSpec, calls Nemotron to reason over steps, then executes them.
Action tier is driven by risk_level only — not by incident type labels.
Falls back to rule-based when NEMOCLAW_ENABLED=0 or the API call fails.
"""

import json
import os
import time

import requests
from openai import OpenAI

from pipeline.action_agent.dispatcher import ActionSpec

NEMOCLAW_MODEL = "nvidia/nemotron-nano-12b-v2-vl"

EXECUTOR_PROMPT = """\
You are Guardian AI, a security operations agent.

You received a confirmed incident. Nemotron has already analyzed the footage and assigned
a risk_level. Use ONLY risk_level to decide which steps to execute — do not re-classify
based on the incident_type label.

Available step types:
  notify         — push notification to operator
  lock_camera    — lock the camera feed (medium+)
  smart_lock     — engage the physical smart lock on the premises (high+)
  emergency_call — initiate mock 911 call (critical only)
  log            — log only, no action

Tier rules (strict — do not deviate):
  low      → [notify]
  medium   → [notify, lock_camera]
  high     → [notify, lock_camera, smart_lock]
  critical → [notify, lock_camera, smart_lock, emergency_call]

Write the notification message using person_behavior (what Nemotron saw in the footage),
not the incident_type label.

Incident:
{action_spec_json}

Respond ONLY with valid JSON — no markdown, no extra text:
{{
  "steps": [
    {{"type": "notify", "message": "operator-ready message based on what was seen"}},
    {{"type": "lock_camera", "device_id": "..."}},
    {{"type": "smart_lock"}},
    {{"type": "emergency_call"}}
  ],
  "rationale": "one sentence"
}}"""

# Smart lock animation sequence shown on the homepage
SMART_LOCK_SEQUENCE = [
    {"step": 1, "label": "Threat detected",    "status": "done"},
    {"step": 2, "label": "Guardian AI engaged", "status": "done"},
    {"step": 3, "label": "Smart lock engaging", "status": "active"},
    {"step": 4, "label": "Premises secured",    "status": "pending"},
]

# Emergency call animation sequence
EMERGENCY_CALL_SEQUENCE = [
    {"step": 1, "label": "Emergency detected",     "status": "done"},
    {"step": 2, "label": "Contacting authorities", "status": "active"},
    {"step": 3, "label": "Call request sent",      "status": "pending"},
]


class NemoClawExecutor:
    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        bubble_id: str | None = None,
    ) -> None:
        self._sb_url = supabase_url.rstrip("/")
        self._sb_key = supabase_key
        self._bubble_id = bubble_id
        self._enabled = os.getenv("NEMOCLAW_ENABLED", "1") != "0"
        nvidia_key = os.getenv("NVIDIA_API_KEY", "")
        self._client: OpenAI | None = (
            OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=nvidia_key)
            if self._enabled and nvidia_key
            else None
        )

    def execute(self, spec: ActionSpec) -> None:
        if self._client:
            steps, rationale = self._reason(spec)
        else:
            steps, rationale = self._rule_based(spec)

        actions_taken = []
        for step in steps:
            result = self._run_step(step, spec)
            if result:
                actions_taken.append(result)

        if actions_taken:
            print(
                f"[NemoClaw] {spec.incident_id} ({spec.risk_level}) → "
                f"{[a['type'] for a in actions_taken]} — {rationale}"
            )

    # ── LLM reasoning ─────────────────────────────────────────────────────────

    def _reason(self, spec: ActionSpec) -> tuple[list[dict], str]:
        ctx = {
            "risk_level": spec.risk_level,
            "incident_type": spec.incident_type,
            "person_behavior": spec.person_behavior,
            "summary": spec.summary,
            "device_id": spec.device_id,
            "candidate_actions": spec.candidate_actions,
        }
        prompt = EXECUTOR_PROMPT.format(action_spec_json=json.dumps(ctx, indent=2))
        try:
            resp = self._client.chat.completions.create(  # type: ignore[union-attr]
                model=NEMOCLAW_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=400,
            )
            raw = resp.choices[0].message.content.strip()
            if "```" in raw:
                raw = raw.split("```")[1].lstrip("json").strip()
            data = json.loads(raw)
            return data.get("steps", []), data.get("rationale", "")
        except Exception as e:
            print(f"[NemoClaw] LLM failed ({e}), falling back to rules")
            return self._rule_based(spec)

    def _rule_based(self, spec: ActionSpec) -> tuple[list[dict], str]:
        # Route by risk_level, not incident_type
        behavior = spec.person_behavior or spec.summary or "Suspicious activity detected."
        msg = behavior[:120]
        rl = spec.risk_level
        if rl == "low":
            steps: list[dict] = [{"type": "notify", "message": msg}]
        elif rl == "medium":
            steps = [
                {"type": "notify", "message": msg},
                {"type": "lock_camera", "device_id": spec.device_id},
            ]
        elif rl == "high":
            steps = [
                {"type": "notify", "message": msg},
                {"type": "lock_camera", "device_id": spec.device_id},
                {"type": "smart_lock"},
            ]
        else:  # critical
            steps = [
                {"type": "notify", "message": msg},
                {"type": "lock_camera", "device_id": spec.device_id},
                {"type": "smart_lock"},
                {"type": "emergency_call"},
            ]
        return steps, f"Rule-based dispatch for risk_level={rl}"

    # ── Step runners ──────────────────────────────────────────────────────────

    def _run_step(self, step: dict, spec: ActionSpec) -> dict | None:
        t = step.get("type")
        if t == "notify":
            return self._step_notify(step, spec)
        if t == "lock_camera":
            return self._step_lock_camera(step, spec)
        if t == "smart_lock":
            return self._step_smart_lock(spec)
        if t == "emergency_call":
            return self._step_emergency_call(spec)
        if t == "log":
            print(f"[NemoClaw] log: {spec.summary}")
            return {"type": "log", "ts": time.time()}
        return None

    def _step_notify(self, step: dict, spec: ActionSpec) -> dict | None:
        if not self._can_push():
            return None
        message = step.get("message") or spec.person_behavior or spec.summary or "Security alert."
        row: dict = {
            "bubble": self._bubble_id,
            "event_type": "guardian_action",
            "event_subtype": spec.incident_type,
            "risk_level": spec.risk_level,
            "incident_confirmed": True,
            "confidence": float(spec.metadata.get("confidence", 0.0)),
            "metadata": {
                "source": "nemoclaw",
                "message": message,
                "person_behavior": spec.person_behavior,
                "incident_id": spec.incident_id,
                "action": "notify",
            },
        }
        if spec.device_id:
            row["device"] = spec.device_id
        if self._insert(row):
            print("[NemoClaw] notify → Supabase OK")
            return {"type": "notify", "message": message, "ts": time.time()}
        return None

    def _step_lock_camera(self, step: dict, spec: ActionSpec) -> dict | None:
        if not self._can_push():
            return None
        device_id = step.get("device_id") or spec.device_id
        msg = f"Locked by Guardian AI — {spec.person_behavior[:80]}" if spec.person_behavior else "Locked by Guardian AI"
        row: dict = {
            "bubble": self._bubble_id,
            "event_type": "camera_lock",
            "event_subtype": spec.incident_type,
            "risk_level": spec.risk_level,
            "incident_confirmed": True,
            "confidence": float(spec.metadata.get("confidence", 0.0)),
            "metadata": {
                "source": "nemoclaw",
                "person_behavior": spec.person_behavior,
                "incident_id": spec.incident_id,
                "action": "lock_camera",
                "message": msg,
            },
        }
        if device_id:
            row["device"] = device_id
        if self._insert(row):
            print(f"[NemoClaw] camera_lock → Supabase OK")
            return {"type": "lock_camera", "device_id": device_id, "ts": time.time()}
        return None

    def _step_smart_lock(self, spec: ActionSpec) -> dict | None:
        if not self._can_push():
            return None
        msg = f"Smart lock engaged by Guardian AI — {spec.person_behavior[:80]}" if spec.person_behavior else "Smart lock engaged by Guardian AI"
        row: dict = {
            "bubble": self._bubble_id,
            "event_type": "smart_lock",
            "event_subtype": spec.incident_type,
            "risk_level": spec.risk_level,
            "incident_confirmed": True,
            "confidence": float(spec.metadata.get("confidence", 0.0)),
            "metadata": {
                "source": "nemoclaw",
                "action": "lock",
                "incident_id": spec.incident_id,
                "message": msg,
                "sequence": SMART_LOCK_SEQUENCE,
            },
        }
        if spec.device_id:
            row["device"] = spec.device_id
        if self._insert(row):
            print("[NemoClaw] smart_lock → Supabase OK")
            return {"type": "smart_lock", "ts": time.time()}
        return None

    def _step_emergency_call(self, spec: ActionSpec) -> dict | None:
        if not self._can_push():
            return None
        row: dict = {
            "bubble": self._bubble_id,
            "event_type": "emergency_call",
            "event_subtype": spec.incident_type,
            "risk_level": spec.risk_level,
            "incident_confirmed": True,
            "confidence": float(spec.metadata.get("confidence", 0.0)),
            "metadata": {
                "source": "nemoclaw",
                "action": "call_911",
                "incident_id": spec.incident_id,
                "number": "911",
                "status": "initiated",
                "message": f"Emergency call initiated — {spec.person_behavior[:80]}" if spec.person_behavior else "Emergency call initiated",
                "sequence": EMERGENCY_CALL_SEQUENCE,
            },
        }
        if spec.device_id:
            row["device"] = spec.device_id
        if self._insert(row):
            print("[NemoClaw] emergency_call → Supabase OK")
            return {"type": "emergency_call", "ts": time.time()}
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _insert(self, row: dict) -> bool:
        try:
            resp = requests.post(
                f"{self._sb_url}/rest/v1/device_events",
                headers=self._headers(),
                json=row,
                timeout=10,
            )
            if resp.status_code in (200, 201):
                return True
            print(f"[NemoClaw] insert failed {resp.status_code}: {resp.text[:80]}")
        except Exception as e:
            print(f"[NemoClaw] insert error: {e}")
        return False

    def _can_push(self) -> bool:
        return bool(self._sb_url and self._sb_key and self._bubble_id)

    def _headers(self) -> dict:
        return {
            "apikey": self._sb_key,
            "Authorization": f"Bearer {self._sb_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
