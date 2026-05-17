import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

export type GuardianEvent = {
  id: string;
  event_type: string;
  event_subtype: string | null;
  risk_level: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  device: string | null;
};

type UseGuardianEventsReturn = {
  smartLockEvent: GuardianEvent | null;
  emergencyCallEvent: GuardianEvent | null;
  notifications: GuardianEvent[];
  dismissSmartLock: () => void;
  dismissEmergencyCall: () => void;
  dismissNotification: (id: string) => void;
  clearNotifications: () => void;
};

const MAX_NOTIFICATIONS = 8;

export function useGuardianEvents(bubbleId: string): UseGuardianEventsReturn {
  const [smartLockEvent, setSmartLockEvent] = useState<GuardianEvent | null>(null);
  const [emergencyCallEvent, setEmergencyCallEvent] = useState<GuardianEvent | null>(null);
  const [notifications, setNotifications] = useState<GuardianEvent[]>([]);

  useEffect(() => {
    const channel = supabase
      .channel(`guardian-events-${bubbleId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "device_events",
          filter: `bubble=eq.${bubbleId}`,
        },
        (payload) => {
          const row = payload.new as GuardianEvent;
          if (row.event_type === "smart_lock") setSmartLockEvent(row);
          if (row.event_type === "emergency_call") setEmergencyCallEvent(row);
          if (row.event_type === "guardian_action") {
            setNotifications((prev) => {
              if (prev.some((n) => n.id === row.id)) return prev;
              return [row, ...prev].slice(0, MAX_NOTIFICATIONS);
            });
          }
        },
      )
      .subscribe();

    return () => {
      void supabase.removeChannel(channel);
    };
  }, [bubbleId]);

  return {
    smartLockEvent,
    emergencyCallEvent,
    notifications,
    dismissSmartLock: () => setSmartLockEvent(null),
    dismissEmergencyCall: () => setEmergencyCallEvent(null),
    dismissNotification: (id: string) =>
      setNotifications((prev) => prev.filter((n) => n.id !== id)),
    clearNotifications: () => setNotifications([]),
  };
}
