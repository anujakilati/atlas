# Action Agent Pipeline — OpenClaw → NemoClaw

## Goal

After Nemotron-VL produces an `IncidentReport`, feed it into an action agent layer that decides
and executes the correct response. NemoClaw reasons over the report and picks one of the registered
Guardian AI commands to fire.

---

## Success Criteria

| Detected event | What NemoClaw does | Frontend effect |
|---|---|---|
| `loitering` | Sends a push notification to the operator | Toast / alert card appears in Activity feed |
| `suspicious_behavior` | Triggers a camera lock on the frontend | Camera view enters a "locked" state — controls disabled, red border, lock icon overlay |
| `false_alarm` | No-op | Nothing |
| `theft` / `unknown_person` | Sends push notification + marks event as high risk | Activity feed badge, suspect profile flagged |

---

## Current State (What Already Exists)

```
YOLO detection
    ↓
suspicion_scoring / state machine
    ↓
NemotronEngine.analyze_async()          ← pipeline/nemotron_reasoning/engine.py
    ↓
IncidentReport {
  incident_type,   ← "theft|loitering|suspicious_behavior|false_alarm"
  risk_level,      ← "low|medium|high|critical"
  recommended_action,
  person_behavior,
  summary,
  notifications { short, medium, long }
}
    ↓
notifications/alerts.py             ← generates text only, takes no action
    ↓
device_events row inserted to Supabase
```

The gap: nothing downstream reads `incident_type` or `recommended_action` and acts on them.

---

## Proposed Architecture

```
[IncidentReport from NemotronEngine]
        │
        ▼
┌─────────────────────────────────┐
│  OpenClaw  — Action Dispatcher  │   pipeline/action_agent/dispatcher.py
│  Maps incident_type + risk to   │
│  an ActionSpec, passes to       │
│  NemoClaw for final reasoning   │
└─────────────────────────────────┘
        │
        ▼  ActionSpec JSON
┌─────────────────────────────────┐
│  NemoClaw  — Action Executor    │   pipeline/action_agent/executor.py
│  NVIDIA Nemotron text model     │
│  reasons over spec, picks steps │
└─────────────────────────────────┘
        │
        ├── notify       → insert row to device_events → Supabase Realtime → frontend toast
        ├── lock_camera  → insert row with event_type="camera_lock" → frontend reads & locks UI
        └── update_db    → upsert metadata.action_taken on the original event row
```

---

## Action Mapping (OpenClaw Rules)

OpenClaw maps `incident_type` to a candidate action set. NemoClaw then reasons over the
context and picks the final steps.

| `incident_type` | Candidate Actions | Default NemoClaw Choice |
|---|---|---|
| `loitering` | notify, log | **notify** |
| `suspicious_behavior` | notify, lock_camera | **lock_camera** |
| `theft` | notify, call_security | **notify + call_security** |
| `false_alarm` | log | **log** (no-op) |
| `unknown_person` (from Guardian AI rule) | notify | **notify** |

---

## Step Types (NemoClaw Executor)

| Step type | What happens |
|---|---|
| `notify` | Insert a `device_events` row with `event_type="guardian_action"` and `metadata.message` → Supabase Realtime pushes it to the frontend |
| `lock_camera` | Insert a `device_events` row with `event_type="camera_lock"` and `metadata.device_id` → frontend subscribes and enters locked state |
| `call_security` | POST to `SECURITY_WEBHOOK_URL` env var (no-op if unset) |
| `log` | Write to structured log only, no DB write |
| `update_db` | Upsert `metadata.action_taken` list on the triggering event row |

---

## NemoClaw Prompt

```python
EXECUTOR_PROMPT = """
You are Guardian AI, a security operations agent.

You received a confirmed incident. Choose the correct response steps from the available
action types: notify, lock_camera, call_security, log.

Rules:
- loitering → notify only
- suspicious_behavior → lock_camera (and notify)
- false_alarm → log only
- theft or high/critical risk → notify + call_security

Incident context:
{action_spec_json}

Respond ONLY with valid JSON:
{
  "steps": [
    {"type": "notify", "message": "short operator-ready message"},
    {"type": "lock_camera", "device_id": "..."}
  ],
  "rationale": "one sentence"
}
"""
```

Model: `nvidia/llama-3.1-nemotron-70b-instruct` (same NVIDIA API key already in use).

---

## Frontend: Camera Lock State

When a `camera_lock` event arrives via Supabase Realtime in `CameraIndividualView` /
`DeviceLivePlayer`:

- Red border ring appears around the camera feed
- Lock icon overlay in the top-right corner
- Camera controls (PTZ, record button) are disabled
- A banner: **"Locked by Guardian AI — suspicious activity detected"**
- An "Unlock" button that inserts a `camera_unlock` event and clears the state

Supabase Realtime subscription listens on `device_events` filtered by
`event_type=camera_lock` and `device=<current device id>`.

---

## Frontend: Guardian AI Watchlist Page (Already Exists)

The page at `vault.$bubbleId/commands` (`commands.tsx`) already shows the Guardian AI rules.
Add a second section below the command list: **"Recent AI Actions"**.

```
Guardian AI
Watch list                                        4 active
────────────────────────────────────────────────────────────
[Your family is safe]
AI is monitoring 4 cameras in real time

[Teach a new rule input]

Commands
  ┌─ Child unattended ──────────────────── toggle ─┐
  ├─ Person hurt ───────────────────────── toggle ─┤
  └─ ...                                           ┘

Recent AI Actions                              ← new section
  ┌─ 🔒 Camera locked        12:46 PM ──────────────┐
  │    Suspicious behavior detected — front door     │
  │    "A person in black hoodie reached toward..."  │
  ├─ 🔔 Notification sent     12:42 PM ──────────────┤
  │    Loitering detected — parking lot              │
  └──────────────────────────────────────────────────┘
```

Data source: query `device_events` where `event_type = 'guardian_action'` or
`event_type = 'camera_lock'`, ordered by `created_at DESC`, limit 10. Read from
`metadata.action_taken[].rationale` for the description line.

This is a read-only Supabase query — no new columns, no schema changes.

---

## Integration Point in `engine.py`

```python
# After cb(report) fires (line ~117 in engine.py), add:
from pipeline.action_agent.dispatcher import ActionDispatcher
_dispatcher = ActionDispatcher()   # module-level singleton

if report.incident_confirmed and report.incident_type != "false_alarm":
    _dispatcher.dispatch_async(report)
```

`dispatch_async` uses the same queue/background-thread pattern as `NemotronEngine` — never
blocks the real-time loop.

---

## Config / Env Vars to Add

```bash
# Security webhook (optional — steps that use it are skipped if unset)
SECURITY_WEBHOOK_URL=https://your-security-system/api/alert

# Set to "0" to skip NemoClaw LLM call and use rule-based dispatch only
NEMOCLAW_ENABLED=1

# Reuses the existing NVIDIA_API_KEY
```

---

## New Files

| File | Purpose |
|---|---|
| `pipeline/action_agent/__init__.py` | Empty |
| `pipeline/action_agent/dispatcher.py` | OpenClaw — builds `ActionSpec` from `IncidentReport` |
| `pipeline/action_agent/executor.py` | NemoClaw — calls NVIDIA API, runs steps |

---

## Files Modified

| File | Change |
|---|---|
| `pipeline/nemotron_reasoning/engine.py` | Call `dispatcher.dispatch_async(report)` in callback |
| `backend/config.py` | Add `SECURITY_WEBHOOK_URL`, `NEMOCLAW_ENABLED` |
| `atlas-app/src/routes/vault.$bubbleId.commands.tsx` | Add "Recent AI Actions" section, query `device_events` |
| `atlas-app/src/components/devices/CameraIndividualView.tsx` | Subscribe to `camera_lock` events, render locked UI state |
| `atlas-app/src/components/devices/DeviceLivePlayer.tsx` | Same camera lock subscription (whichever component renders the feed) |

---

## Implementation Order

1. **`dispatcher.py`** — `ActionSpec` dataclass + rule-based mapping (no API, no DB)
2. **`executor.py`** — step runner with hardcoded steps first (no LLM yet), writes to Supabase
3. **Wire `engine.py`** — call `dispatch_async` after the Nemotron callback
4. **Test loitering path** — confirm `guardian_action` row appears in Supabase and toast fires
5. **Test suspicious_behavior path** — confirm `camera_lock` row appears and frontend locks
6. **Add NemoClaw reasoning** — replace hardcoded steps with the NVIDIA API call
7. **Guardian AI Watchlist section** — add "Recent AI Actions" to `commands.tsx`
