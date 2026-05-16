export type DeviceEvent = {
  id: string;
  created_at: string;
  event_type: string;
  event_subtype: string | null;
  risk_level: string | null;
  confidence: number | null;
  incident_confirmed: boolean;
  metadata: Record<string, unknown>;
  bubble: string;
  device: string | null;
  recording_id: string | null;
};

export type Character = {
  id: number;
  created_at: string;
  profile_crop_url: string | null;
  sus_character_description: string | null;
};

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.replace(/\/$/, "");
const SERVICE_KEY = import.meta.env.VITE_SUPABASE_SERVICE_KEY;

function authHeaders() {
  return {
    apikey: SERVICE_KEY,
    Authorization: `Bearer ${SERVICE_KEY}`,
    "Content-Type": "application/json",
  };
}

export async function fetchDeviceEvents(bubbleId: string): Promise<DeviceEvent[]> {
  const res = await fetch(
    `${SUPABASE_URL}/rest/v1/device_events?select=*&bubble=eq.${bubbleId}&order=created_at.desc&limit=100`,
    { headers: authHeaders() }
  );
  if (!res.ok) {
    const text = await res.text();
    console.error(`[fetchDeviceEvents] ${res.status}:`, text);
    throw new Error(`device_events fetch failed: ${res.status}`);
  }
  return res.json() as Promise<DeviceEvent[]>;
}

export async function fetchCharacters(): Promise<Character[]> {
  const res = await fetch(
    `${SUPABASE_URL}/rest/v1/characters?select=*&order=created_at.desc&limit=100`,
    { headers: authHeaders() }
  );
  if (!res.ok) {
    const text = await res.text();
    console.error(`[fetchCharacters] ${res.status}:`, text);
    throw new Error(`characters fetch failed: ${res.status}`);
  }
  return res.json() as Promise<Character[]>;
}
