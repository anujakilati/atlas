export type Activity = {
  id: number;
  created_at: string;
  recording_url: string | null;
  cam_name: string | null;
  reason: string | null;
};

export type Character = {
  id: number;
  created_at: string;
  profile_crop_url: string | null;
  sus_character_description: string | null;
  activity_characters: { activities: { cam_name: string | null } | null }[];
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

export async function fetchActivities(): Promise<Activity[]> {
  const res = await fetch(
    `${SUPABASE_URL}/rest/v1/activities?select=id,created_at,recording_url,cam_name,reason&order=created_at.desc&limit=100`,
    { headers: authHeaders() }
  );
  if (!res.ok) throw new Error(`activities fetch failed: ${res.status}`);
  return res.json() as Promise<Activity[]>;
}

export async function fetchCharacters(): Promise<Character[]> {
  const res = await fetch(
    `${SUPABASE_URL}/rest/v1/characters?select=*,activity_characters(activities(cam_name))&order=created_at.desc&limit=100`,
    { headers: authHeaders() }
  );
  if (!res.ok) throw new Error(`characters fetch failed: ${res.status}`);
  return res.json() as Promise<Character[]>;
}
