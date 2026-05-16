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

// During SSR (Node.js dev server), WebSocketFactory.getWebSocketConstructor() throws
// because Node.js < 22 has no native WebSocket. Provide a stub transport to skip
// that check. Auth is also configured to avoid browser-only APIs on the server.
const isBrowser = typeof window !== "undefined";

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: isBrowser,
    autoRefreshToken: isBrowser,
    detectSessionInUrl: isBrowser,
    skipAutoInitialize: !isBrowser,
  },
  ...(!isBrowser && {
    realtime: {
      // Realtime is browser-only; this stub prevents the WebSocket constructor
      // lookup from throwing when the client is instantiated during SSR.
      transport: class NoopWS {} as unknown as typeof WebSocket,
    },
  }),
});

export async function clearLocalAuthSession() {
  await supabase.auth.signOut({ scope: "local" });
}
