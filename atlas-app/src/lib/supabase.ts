import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL?.replace(/\/$/, "");
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!supabaseUrl?.startsWith("https://") || !supabaseAnonKey) {
  throw new Error("Set VITE_SUPABASE_URL (https://<ref>.supabase.co) and VITE_SUPABASE_ANON_KEY in .env");
}

function projectRefFromKey(key: string) {
  try {
    const payload = JSON.parse(atob(key.split(".")[1] ?? "")) as { ref?: string };
    return payload.ref ?? null;
  } catch {
    return null;
  }
}

const projectRef = projectRefFromKey(supabaseAnonKey);
if (projectRef && !supabaseUrl.includes(projectRef)) {
  throw new Error(
    `VITE_SUPABASE_URL must match your anon key project. Use https://${projectRef}.supabase.co`,
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});

export async function clearLocalAuthSession() {
  await supabase.auth.signOut({ scope: "local" });
}
