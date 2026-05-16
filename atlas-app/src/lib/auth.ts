import { supabase } from "@/lib/supabase";

export type UserProfile = {
  id: string;
  email: string;
  name: string;
};

export async function fetchUserProfile(userId: string) {
  const { data, error } = await supabase.from("users").select("id, email, name").eq("id", userId).maybeSingle();
  if (error) throw error;
  return data;
}

export async function signUp(email: string, password: string, name: string) {
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { data: { name } },
  });
  if (error) throw error;
  return data;
}

export async function signIn(email: string, password: string) {
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw error;
  return data;
}

export async function signOut() {
  const { error } = await supabase.auth.signOut();
  if (error) throw error;
}
