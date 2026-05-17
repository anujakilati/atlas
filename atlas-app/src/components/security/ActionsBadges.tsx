import { Bell, Home, Phone, CheckCircle, MinusCircle, ShieldCheck, Circle } from "lucide-react";
import type { DeviceEvent } from "@/lib/activities";

const ACTION_TYPES = new Set(["guardian_action", "camera_lock", "smart_lock", "emergency_call"]);

type Props = {
  incidentId: string;
  event: DeviceEvent;
  allEvents: DeviceEvent[];
};

type ActionLine = {
  icon: typeof Bell;
  label: string;
};

const ACTION_CONFIG: Record<string, ActionLine> = {
  guardian_action: { icon: Bell,  label: "Notification sent to operator" },
  smart_lock:      { icon: Home,  label: "Smart lock engaged — premises secured" },
  emergency_call:  { icon: Phone, label: "911 call initiated" },
};

const ACTION_ORDER = ["guardian_action", "smart_lock", "emergency_call"];

// Tier of actions Nemotron should have triggered for a given risk_level
const EXPECTED_TIER: Record<string, string[]> = {
  low:      ["guardian_action"],
  medium:   ["guardian_action"],
  high:     ["guardian_action", "smart_lock"],
  critical: ["guardian_action", "smart_lock", "emergency_call"],
};

const TIME_WINDOW_MS = 60_000; // 60s after the incident event

function findActionsForIncident(
  event: DeviceEvent,
  incidentId: string,
  allEvents: DeviceEvent[],
): DeviceEvent[] {
  // Primary: match by metadata.incident_id
  let matched = allEvents.filter(
    (ev) =>
      ACTION_TYPES.has(ev.event_type) &&
      (ev.metadata?.incident_id as string | undefined) === incidentId,
  );
  if (matched.length > 0) return matched;

  // Fallback: action events created within 60s after this event on the same device/bubble
  const eventTs = new Date(event.created_at).getTime();
  matched = allEvents.filter((ev) => {
    if (!ACTION_TYPES.has(ev.event_type)) return false;
    if (event.device && ev.device && ev.device !== event.device) return false;
    if (ev.bubble !== event.bubble) return false;
    const dt = new Date(ev.created_at).getTime() - eventTs;
    return dt >= -2_000 && dt <= TIME_WINDOW_MS;
  });
  return matched;
}

export function ActionsBadges({ incidentId, event, allEvents }: Props) {
  const actions = findActionsForIncident(event, incidentId, allEvents);

  // Deduplicate by event_type
  const seen = new Set<string>();
  const unique = actions.filter((a) => {
    if (seen.has(a.event_type)) return false;
    seen.add(a.event_type);
    return true;
  });
  unique.sort((a, b) => ACTION_ORDER.indexOf(a.event_type) - ACTION_ORDER.indexOf(b.event_type));

  const isFalseAlarm = event.event_type === "false_alarm";
  const risk = event.risk_level ?? "low";
  const expected = EXPECTED_TIER[risk] ?? [];

  // What to render:
  //  - false_alarm → "No action taken"
  //  - low risk + no fired actions → "No action taken"
  //  - any tier with fired actions → bullet list of what fired (✓)
  //  - medium+ tier without fired actions → bullet list of expected tier (○ pending)
  const noActionTaken = isFalseAlarm || (unique.length === 0 && risk === "low");

  if (unique.length === 0 && !noActionTaken && expected.length === 0) return null;

  // Build display list: union of fired + expected (in canonical order)
  const firedTypes = new Set(unique.map((u) => u.event_type));
  const displayTypes = unique.length > 0
    ? unique.map((u) => u.event_type)
    : expected;

  return (
    <div className="mt-3 rounded-xl border border-border/60 bg-background/40 px-3 py-2">
      <div className="mb-1.5 flex items-center gap-1.5">
        <ShieldCheck className="h-3 w-3 text-gold" />
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Guardian AI response
        </p>
      </div>
      {noActionTaken ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <MinusCircle className="h-3.5 w-3.5 shrink-0" />
          <span>No action taken — incident assessed as non-threatening</span>
        </div>
      ) : (
        <ul className="space-y-1">
          {displayTypes.map((type) => {
            const cfg = ACTION_CONFIG[type];
            if (!cfg) return null;
            const Icon = cfg.icon;
            const fired = firedTypes.has(type);
            const isCritical = type === "smart_lock" || type === "emergency_call";
            return (
              <li key={type} className="flex items-center gap-2 text-xs">
                {fired ? (
                  <CheckCircle className="h-3.5 w-3.5 shrink-0 text-success" />
                ) : (
                  <Circle className="h-3.5 w-3.5 shrink-0 text-muted-foreground/40" />
                )}
                <Icon
                  className={`h-3.5 w-3.5 shrink-0 ${
                    !fired ? "text-muted-foreground/50" : isCritical ? "text-danger" : "text-foreground/70"
                  }`}
                />
                <span
                  className={
                    !fired
                      ? "text-muted-foreground"
                      : isCritical
                      ? "font-medium text-foreground"
                      : "text-foreground/85"
                  }
                >
                  {cfg.label}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** Returns true if ev is an internal NemoClaw action event (not a real incident). */
export function isActionEvent(ev: DeviceEvent): boolean {
  return ACTION_TYPES.has(ev.event_type);
}
