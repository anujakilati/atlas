import { Bell, Lock, Home, Phone } from "lucide-react";
import type { DeviceEvent } from "@/lib/activities";

const ACTION_TYPES = new Set(["guardian_action", "camera_lock", "smart_lock", "emergency_call"]);

type Props = {
  incidentId: string;
  allEvents: DeviceEvent[];
};

type Badge = {
  type: string;
  icon: typeof Bell;
  label: string;
  color: string;
};

const BADGE_CONFIG: Record<string, Omit<Badge, "type">> = {
  guardian_action: { icon: Bell,  label: "Notification sent",   color: "bg-gold/15 text-gold" },
  camera_lock:     { icon: Lock,  label: "Camera locked",       color: "bg-danger/15 text-danger" },
  smart_lock:      { icon: Home,  label: "Smart lock engaged",  color: "bg-danger/15 text-danger" },
  emergency_call:  { icon: Phone, label: "911 call initiated",  color: "bg-danger/20 text-danger" },
};

export function ActionsBadges({ incidentId, allEvents }: Props) {
  // Find action events that reference this incident
  const actions = allEvents.filter(
    (ev) =>
      ACTION_TYPES.has(ev.event_type) &&
      (ev.metadata?.incident_id as string | undefined) === incidentId,
  );

  if (actions.length === 0) return null;

  // Deduplicate by event_type (show each action type once)
  const seen = new Set<string>();
  const unique = actions.filter((a) => {
    if (seen.has(a.event_type)) return false;
    seen.add(a.event_type);
    return true;
  });

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {unique.map((a) => {
        const cfg = BADGE_CONFIG[a.event_type];
        if (!cfg) return null;
        const Icon = cfg.icon;
        return (
          <span
            key={a.id}
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${cfg.color}`}
          >
            <Icon className="h-3 w-3" />
            {cfg.label}
          </span>
        );
      })}
    </div>
  );
}

/** Returns true if ev is an internal NemoClaw action event (not a real incident). */
export function isActionEvent(ev: DeviceEvent): boolean {
  return ACTION_TYPES.has(ev.event_type);
}
