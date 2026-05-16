# Autonomous Action System — NemoClaw Risk Tiers

## Goal

Nemotron judges the risk level of every confirmed incident. NemoClaw then executes a tier-matched
action sequence autonomously. Each tier escalates both the severity of the response and the
surfaces it touches (notification → camera lock → smart lock → emergency call). Every action
taken is reflected in real-time on the frontend.

---

## How Risk Level Is Decided

Nemotron VLM already analyzes the raw frames and produces a natural-language `person_behavior`
description plus a `risk_level` (`low/medium/high/critical`). We do not classify by label
(loitering, theft, etc.) — we trust Nemotron's judgment of what it sees in the image.

NemoClaw then reads only `risk_level` to decide what tier of actions to execute. The
`incident_type` label is used only for display purposes, not for routing decisions.

This means:
- A person standing outside for a long time → Nemotron may call it `loitering` with `risk_level=low` → notify only, nothing extreme
- The same person seen grabbing someone → Nemotron reads the image and may assign `risk_level=critical` regardless of the classification label → full response

---

## Risk Tier Matrix

| Nemotron `risk_level` | NemoClaw Actions |
|---|---|
| `low` | Push notification only |
| `medium` | Notification + camera lock |
| `high` | Notification + camera lock + smart lock |
| `critical` | Notification + camera lock + smart lock + mock 911 call |

No label-to-tier mapping. No overrides. Risk level from Nemotron = tier, full stop.

---

## Action Sequence Per Tier

### Low (`risk_level=low`)
```
1. notify      → insert guardian_action row → push notification toast in app
```

### Medium (`risk_level=medium`)
```
1. notify      → push notification toast
2. lock_camera → insert camera_lock row → camera view goes red + locked overlay
```

### High (`risk_level=high`)
```
1. notify
2. lock_camera
3. smart_lock  → insert smart_lock row → homepage SlideToLock animates to locked
                 → "Locked by Guardian AI" status badge appears
                 → sequence of steps shown on homepage and under activity card
```

### Critical (`risk_level=critical`)
```
1. notify
2. lock_camera
3. smart_lock
4. emergency_call → insert emergency_call row → mock 911 call modal appears
                   → "Call request sent to authorities" shown in UI
                   → sequence steps: Dialing → Connecting → Connected (animated)
```

---

## New device_events Row Types

### `smart_lock`
```json
{
  "event_type": "smart_lock",
  "event_subtype": "theft",
  "risk_level": "high",
  "incident_confirmed": true,
  "metadata": {
    "source": "nemoclaw",
    "action": "lock",
    "incident_id": "...",
    "message": "Locked by Guardian AI — theft detected",
    "sequence": [
      { "step": 1, "label": "Threat detected",     "status": "done",    "ts": 1234567890 },
      { "step": 2, "label": "Guardian AI engaged",  "status": "done",    "ts": 1234567891 },
      { "step": 3, "label": "Smart lock engaging",  "status": "active",  "ts": 1234567892 },
      { "step": 4, "label": "Premises secured",     "status": "pending", "ts": null }
    ]
  }
}
```

### `emergency_call`
```json
{
  "event_type": "emergency_call",
  "event_subtype": "kidnapping",
  "risk_level": "critical",
  "incident_confirmed": true,
  "metadata": {
    "source": "nemoclaw",
    "action": "call_911",
    "incident_id": "...",
    "number": "911",
    "status": "initiated",
    "sequence": [
      { "step": 1, "label": "Emergency detected",       "status": "done",    "ts": 1234567890 },
      { "step": 2, "label": "Contacting authorities",   "status": "active",  "ts": 1234567891 },
      { "step": 3, "label": "Call request sent",        "status": "pending", "ts": null }
    ]
  }
}
```

---

## Backend Changes

### `pipeline/action_agent/dispatcher.py`

Drop the incident-type map entirely. Route purely on `risk_level`:

```python
TIER_ACTIONS = {
    "low":      ["notify"],
    "medium":   ["notify", "lock_camera"],
    "high":     ["notify", "lock_camera", "smart_lock"],
    "critical": ["notify", "lock_camera", "smart_lock", "emergency_call"],
}

# In ActionDispatcher.dispatch_async():
candidate_actions = TIER_ACTIONS.get(report.risk_level, ["notify"])
```

`incident_type` is passed through to the ActionSpec only so the executor can use it
in the notification message and for display — it does not affect which steps run.

### `pipeline/action_agent/executor.py`

Add two new step runners:

#### `_step_smart_lock`
Inserts a `smart_lock` event to Supabase with a 4-step sequence. Steps animate on the frontend
as the Realtime event arrives.

#### `_step_emergency_call`
Inserts an `emergency_call` event to Supabase with a 3-step sequence. This is mock only —
no real call is placed. The frontend shows the animated call sequence.

Update `EXECUTOR_PROMPT` to be risk-level driven, not label driven:
```
You are given the risk_level that Nemotron assigned after analyzing the actual footage.
Do not re-classify based on the incident_type label — use risk_level to decide steps.

  low      → notify only
  medium   → notify + lock_camera
  high     → notify + lock_camera + smart_lock
  critical → notify + lock_camera + smart_lock + emergency_call

Use person_behavior (the visual description from the footage) to write the
notification message — not the incident_type label.
```

---

## Frontend Changes

### 1. Activity Page — "Actions Taken" under each event card

Each event card gets an expandable row of action badges below the description:

```
Suspicious Person                           9:42 AM
A person wearing a black hoodie...
Front Door · high risk

┌─ Actions taken ─────────────────────────────┐
│  🔔 Notification sent                        │
│  🔒 Camera locked                            │
│  🏠 Smart lock engaged                       │
└──────────────────────────────────────────────┘
```

Data source: query `device_events` where
`metadata->>'incident_id' = eq.<incident_id>` and
`event_type = in.(guardian_action, camera_lock, smart_lock, emergency_call)`.

These are fetched alongside events (one extra query per visible event, batched).

### 2. Homepage — Smart Lock Realtime Response

`vault.$bubbleId.index.tsx` currently has a manual `SlideToLock` widget. Wire it to Supabase
Realtime:

- Subscribe to `device_events` INSERT where `bubble=eq.<bubbleId>` and
  `event_type=eq.smart_lock`
- When a `smart_lock` event arrives:
  - Animate `SlideToLock` to the locked position (set `locked=true`)
  - Replace the "Secured / Unlocked" badge with **"Locked by Guardian AI"** in danger/red
  - Show a `SmartLockSequence` card below the lock widget:

```
┌─ Guardian AI — Smart Lock Sequence ─────────────┐
│  ✓  Threat detected                              │
│  ✓  Guardian AI engaged                          │
│  ◎  Smart lock engaging...          (animated)   │
│  ○  Premises secured                (pending)    │
└──────────────────────────────────────────────────┘
```

Steps animate in with 800ms delays between each one (CSS transition, no real API calls).
A "Dismiss" button clears the card and inserts a `smart_unlock` event.

### 3. Homepage — Emergency Call Modal (Critical only)

Subscribe to `device_events` INSERT where `event_type=eq.emergency_call`:

```
┌─────────────────────────────────────────────────┐
│  🚨  Emergency Call Initiated                    │
│                                                  │
│       📞  911                                    │
│                                                  │
│  ✓  Emergency detected                           │
│  ◎  Contacting authorities...       (animated)   │
│  ○  Call request sent               (pending)    │
│                                                  │
│  [Dismiss]                                       │
└─────────────────────────────────────────────────┘
```

Rendered as a fixed overlay (z-50) that appears over the homepage. Dismisses after 30s or on
tap. No real call is placed.

### 4. Today Section on Homepage — Live Activity Feed

Replace the hardcoded `ActivityRow` items with real Supabase data: query the 5 most recent
`device_events` for the bubble (excluding `guardian_action`, `camera_lock`, `smart_lock`,
`emergency_call` internal types). Format titles using the same `EVENT_LABELS` map from the
Activity page.

---

## New Files

| File | Purpose |
|---|---|
| `atlas-app/src/components/security/SmartLockSequence.tsx` | Animated step sequence card for homepage |
| `atlas-app/src/components/security/EmergencyCallModal.tsx` | Fixed overlay for critical incidents |
| `atlas-app/src/components/security/ActionsBadges.tsx` | "Actions taken" row under activity cards |
| `atlas-app/src/hooks/use-guardian-events.ts` | Supabase Realtime hook for smart_lock + emergency_call events |

---

## Modified Files

| File | Change |
|---|---|
| `pipeline/action_agent/dispatcher.py` | Add full tier map + tier resolution logic |
| `pipeline/action_agent/executor.py` | Add `smart_lock` + `emergency_call` step runners, update prompt |
| `atlas-app/src/routes/vault.$bubbleId.index.tsx` | Wire SmartLock Realtime, replace hardcoded activity, add emergency modal |
| `atlas-app/src/routes/vault.$bubbleId.activity.tsx` | Add "Actions taken" badges under each event card |

---

## Implementation Order

1. **Backend tiers** — update `dispatcher.py` tier map + `executor.py` new step runners
2. **Test** — run `scripts/test_action_agent.py` with `incident_type=theft` (high) and
   `incident_type=kidnapping` (critical), confirm correct Supabase rows appear
3. **`use-guardian-events.ts`** — Realtime hook that surfaces `smart_lock` + `emergency_call`
   rows for a given bubble
4. **`SmartLockSequence.tsx`** — animated step card component
5. **`EmergencyCallModal.tsx`** — critical overlay component
6. **Wire homepage** — replace hardcoded activity + connect Realtime lock/call state
7. **`ActionsBadges.tsx`** — query related action rows per incident_id, render under cards
8. **Wire activity page** — attach badges to each event card
