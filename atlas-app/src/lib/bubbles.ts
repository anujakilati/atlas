import { appendBubbleToUser, fetchUserProfile } from "@/lib/auth";
import { supabase } from "@/lib/supabase";

function formatDbError(err: unknown, fallback: string) {
  const message = err instanceof Error ? err.message : fallback;
  if (/row-level security|42501|403|permission denied/i.test(message)) {
    return "Database permission denied. Run supabase/bubbles.sql in Supabase SQL Editor (needs SELECT + INSERT policies).";
  }
  if (/PGRST202|could not find the function|404/i.test(message)) {
    return "Missing database function. Run supabase/users.sql in Supabase SQL Editor (creates add_bubble_to_user).";
  }
  if (/409|duplicate key|already exists/i.test(message)) {
    return message;
  }
  return message || fallback;
}

export type BubbleType = "house" | "store" | "school";

export type Bubble = {
  id: string;
  name: string;
  type: BubbleType;
  members: string[];
  devices: string[];
  isOwner: boolean;
};

type BubbleRow = {
  id: string;
  name: string;
  members: string[] | null;
  devices: string[] | null;
  invite_token: string | null;
};

export function generateInviteToken() {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  return Array.from({ length: 6 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
}

function inferType(name: string): BubbleType {
  const n = name.toLowerCase();
  if (n.includes("store") || n.includes("shop")) return "store";
  if (n.includes("school") || n.includes("campus")) return "school";
  return "house";
}

function toBubble(row: BubbleRow, userId: string): Bubble {
  const members = row.members ?? [];
  return {
    id: row.id,
    name: row.name,
    type: inferType(row.name),
    members,
    devices: row.devices ?? [],
    isOwner: members[0] === userId,
  };
}

async function getCurrentUser() {
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error("You must be logged in.");
  return user;
}

/** Load bubbles where the user is in members; sync ids into users.bubbles when possible. */
export async function fetchMyBubbles() {
  const user = await getCurrentUser();

  const { data, error } = await supabase
    .from("bubbles")
    .select("id, name, members, devices")
    .contains("members", [user.id])
    .order("created_at", { ascending: false });

  if (error) throw new Error(formatDbError(error, "Could not load bubbles."));

  const bubbles = (data as BubbleRow[]).map((row) => toBubble(row, user.id));

  await Promise.all(
    bubbles.map(async (bubble) => {
      try {
        await appendBubbleToUser(bubble.id);
      } catch {
        // RPC may be missing; dashboard still works from members list
      }
    }),
  );

  return bubbles;
}

export async function createBubble(name: string, type: BubbleType) {
  const user = await getCurrentUser();

  const label = type === "house" ? "Home" : type === "store" ? "Store" : "School";
  const bubbleName = name.trim() ? `${label} — ${name.trim()}` : `My ${label}`;

  const inviteToken = generateInviteToken();

  const { data, error } = await supabase
    .from("bubbles")
    .insert({
      name: bubbleName,
      members: [user.id],
      devices: [],
      invite_token: inviteToken,
    })
    .select("id, name, members, devices, invite_token")
    .single();

  if (error) throw new Error(formatDbError(error, "Could not create bubble."));

  const bubble = toBubble(data as BubbleRow, user.id);

  try {
    await appendBubbleToUser(bubble.id);
  } catch (appendError) {
    throw new Error(formatDbError(appendError, "Bubble created but could not link to your profile. Run supabase/users.sql."));
  }

  return bubble;
}

export async function getBubbleInviteToken(bubbleId: string, regenerate = false) {
  await getCurrentUser();

  if (!regenerate) {
    const { data, error } = await supabase
      .from("bubbles")
      .select("invite_token")
      .eq("id", bubbleId)
      .single();

    if (error) throw new Error(formatDbError(error, "Could not load invite code."));
    if (data.invite_token) return data.invite_token;
  }

  const inviteToken = generateInviteToken();
  const { error: updateError } = await supabase
    .from("bubbles")
    .update({ invite_token: inviteToken })
    .eq("id", bubbleId);

  if (updateError) throw new Error(formatDbError(updateError, "Could not generate invite code."));
  return inviteToken;
}

export async function joinBubbleByToken(token: string) {
  const code = token.trim().toUpperCase();
  if (!code) throw new Error("Enter an invite code.");

  const { data, error } = await supabase.rpc("join_bubble_by_token", { p_token: code });

  if (!error) {
    try {
      await appendBubbleToUser(data as string);
    } catch {
      // RPC may have updated users.bubbles
    }
    return data as string;
  }

  if (/PGRST202|could not find the function|404/i.test(error.message ?? "")) {
    throw new Error("Join by code is not set up yet. Run the latest supabase/bubbles.sql in Supabase SQL Editor.");
  }

  throw new Error(formatDbError(error, "Could not join bubble."));
}

async function joinBubbleById(bubbleId: string) {
  const { data, error } = await supabase.rpc("join_bubble_by_id", { p_bubble_id: bubbleId });
  if (error) throw error;

  try {
    await appendBubbleToUser(data as string);
  } catch {
    // already added by RPC
  }

  return data as string;
}

/** @deprecated Use joinBubbleByToken */
export async function joinBubble(token: string) {
  if (token.length <= 8 && /^[A-Z0-9]+$/i.test(token)) {
    return joinBubbleByToken(token);
  }
  return joinBubbleById(token.trim());
}

export async function fetchBubble(bubbleId: string) {
  const user = await getCurrentUser();

  const { data, error } = await supabase
    .from("bubbles")
    .select("id, name, members, devices")
    .eq("id", bubbleId)
    .single();

  if (error) throw error;

  const bubble = toBubble(data as BubbleRow, user.id);
  if (!bubble.members.includes(user.id)) {
    throw new Error("You are not a member of this bubble.");
  }

  const profile = await fetchUserProfile(user.id);
  if (!profile?.bubbles.includes(bubbleId)) {
    await appendBubbleToUser(bubbleId);
  }

  return bubble;
}
