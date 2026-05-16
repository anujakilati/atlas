import type { User } from "@supabase/supabase-js";
import { isAuthApiError } from "@supabase/supabase-js";
import { clearLocalAuthSession, supabase } from "@/lib/supabase";

export function formatAuthError(err: unknown): string {
  if (isAuthApiError(err)) {
    if (err.status === 403) {
      return "Session expired or invalid. Refresh the page and log in again.";
    }
    if (err.status === 400 && /invalid login credentials/i.test(err.message)) {
      return "Wrong email or password. If you just signed up, confirm your email or disable “Confirm email” in Supabase.";
    }
    if (/email not confirmed/i.test(err.message)) {
      return "Confirm your email first, or disable “Confirm email” under Supabase → Authentication → Providers → Email.";
    }
    return err.message;
  }

  const message = err instanceof Error ? err.message : "Something went wrong.";

  if (/rate limit|too many requests|429/i.test(message)) {
    return "Email rate limit exceeded. Wait ~1 hour, or disable “Confirm email” in Supabase.";
  }

  if (/already registered|already been registered/i.test(message)) {
    return "An account with this email already exists. Try logging in instead.";
  }

  if (/permission denied|row-level security|42501|403/i.test(message)) {
    return "Database permission denied. Run supabase/users.sql in the SQL Editor (RLS + grants), then log in again.";
  }

  return message;
}

export type UserProfile = {
  id: string;
  username: string;
  bubbles: string[];
};

function usernameFromUser(user: User, fallback?: string) {
  return (
    fallback?.trim() ||
    (typeof user.user_metadata?.name === "string" ? user.user_metadata.name : "") ||
    user.email?.split("@")[0] ||
    "user"
  );
}

async function requireSession() {
  const {
    data: { session },
    error,
  } = await supabase.auth.getSession();

  if (error || !session) {
    await clearLocalAuthSession();
    throw new Error("You must be logged in.");
  }

  return session;
}

export async function upsertUserProfile(user: User, username?: string) {
  await requireSession();

  const existing = await fetchUserProfile(user.id);

  const { error } = await supabase.from("users").upsert(
    {
      id: user.id,
      username: usernameFromUser(user, username),
      bubbles: existing?.bubbles ?? [],
    },
    { onConflict: "id" },
  );

  if (error) throw error;
}

export async function fetchUserProfile(userId: string) {
  const { data, error } = await supabase.from("users").select("id, username, bubbles").eq("id", userId).maybeSingle();
  if (error) throw error;
  if (!data) return null;
  return { ...data, bubbles: data.bubbles ?? [] };
}

function isMissingRpc(error: { code?: string; message?: string }) {
  return (
    error.code === "PGRST202" ||
    /could not find the function|404/i.test(error.message ?? "")
  );
}

/** Appends bubble id to public.users.bubbles for the current user. */
export async function appendBubbleToUser(bubbleId: string) {
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error("You must be logged in.");

  const { error: rpcError } = await supabase.rpc("add_bubble_to_user", { p_bubble_id: bubbleId });

  if (!rpcError) return;

  if (!isMissingRpc(rpcError)) throw rpcError;

  const profile = await fetchUserProfile(user.id);
  const bubbles = profile?.bubbles ?? [];
  if (bubbles.includes(bubbleId)) return;

  const { error } = await supabase
    .from("users")
    .update({ bubbles: [...bubbles, bubbleId] })
    .eq("id", user.id);

  if (error) throw error;
}

export async function signUp(email: string, password: string, name: string) {
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { data: { name } },
  });
  if (error) throw error;

  if (data.session && data.user) {
    await upsertUserProfile(data.user, name);
  } else if (data.user && !data.session) {
    throw new Error(
      "Account created in Auth, but you must confirm email before logging in — or disable “Confirm email” in Supabase → Authentication → Providers → Email. The users.sql trigger will create your profile row.",
    );
  }

  return data;
}

export async function signIn(email: string, password: string) {
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw error;

  if (!data.session) {
    throw new Error("Login succeeded but no session was returned. Check Supabase Auth settings.");
  }

  if (data.user) {
    await upsertUserProfile(data.user);
  }

  return data;
}

export async function signOut() {
  await clearLocalAuthSession();
}

export async function validateSession() {
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser();

  if (error || !user) {
    await clearLocalAuthSession();
    return null;
  }

  return user;
}
