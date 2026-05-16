import { supabase } from "@/lib/supabase";

const BUCKET = "camera-feeds";

function formatDbError(err: unknown, fallback: string) {
  const e = err as { message?: string; details?: string; hint?: string };
  const message = [e.message, e.details, e.hint].filter(Boolean).join(" — ") || fallback;
  if (/device_token|PGRST204.*devices/i.test(message)) {
    return "Devices table needs an update. Run supabase/devices.sql in Supabase SQL Editor.";
  }
  if (/row-level security|42501|403|permission denied/i.test(message)) {
    return "Database permission denied. Run supabase/devices.sql in Supabase SQL Editor.";
  }
  if (/PGRST202|could not find the function/i.test(message)) {
    return "Run supabase/devices.sql in Supabase SQL Editor.";
  }
  return message || fallback;
}

export type Device = {
  id: string;
  bubbleId: string;
  name: string;
  placement: string;
  contact: string;
  deviceToken: string;
  status: "pending" | "online" | "offline";
};

export type RegisteredDevice = {
  id: string;
  name: string;
  placement: string;
  bubbleName: string;
};

export type DeviceRecording = {
  id: string;
  deviceId: string;
  storagePath: string;
  publicUrl: string;
  durationMs: number | null;
  createdAt: string;
};

type DeviceRow = {
  id: string;
  bubble: string;
  name: string;
  placement: string;
  contact: string;
  device_token: string;
  status: string;
};

export const PLACEMENT_OPTIONS = [
  "Front door",
  "Back door",
  "Backyard",
  "Living room",
  "Garage",
  "Bedroom",
  "Kitchen",
  "Office",
  "Hallway",
  "Other",
] as const;

export function generateDeviceToken() {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  return Array.from({ length: 8 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
}

export function liveFeedStoragePath(deviceId: string) {
  return `${deviceId}/live.webm`;
}

export function publicStorageUrl(path: string) {
  const { data } = supabase.storage.from(BUCKET).getPublicUrl(path);
  return data.publicUrl;
}

function toDevice(row: DeviceRow): Device {
  const status = row.status as Device["status"];
  return {
    id: row.id,
    bubbleId: row.bubble,
    name: row.name,
    placement: row.placement,
    contact: row.contact ?? "",
    deviceToken: row.device_token,
    status: status === "online" || status === "offline" ? status : "pending",
  };
}

function isEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function isPhone(value: string) {
  return /^\+?[\d\s().-]{7,}$/.test(value);
}

export function validateContact(contact: string) {
  const trimmed = contact.trim();
  if (!trimmed) return null;
  if (!isEmail(trimmed) && !isPhone(trimmed)) {
    return "Enter a valid email or phone number.";
  }
  return null;
}

export async function fetchBubbleDevices(bubbleId: string) {
  const { data, error } = await supabase
    .from("devices")
    .select("id, bubble, name, placement, contact, device_token, status")
    .eq("bubble", bubbleId)
    .order("created_at", { ascending: false });

  if (error) throw new Error(formatDbError(error, "Could not load devices."));
  return (data as DeviceRow[]).map(toDevice);
}

export async function createDevice(
  bubbleId: string,
  input: { name: string; placement: string; contact?: string },
) {
  const name = input.name.trim();
  const placement = input.placement.trim();
  const contact = (input.contact ?? "").trim();
  if (!name) throw new Error("Enter a device name.");
  if (!placement) throw new Error("Choose a placement.");
  const contactError = validateContact(contact);
  if (contactError) throw new Error(contactError);

  const deviceToken = generateDeviceToken();

  const { data, error } = await supabase
    .from("devices")
    .insert({
      bubble: bubbleId,
      name,
      placement,
      contact,
      device_token: deviceToken,
      status: "pending",
    })
    .select("id, bubble, name, placement, contact, device_token, status")
    .single();

  if (error) throw new Error(formatDbError(error, "Could not add device."));

  const device = toDevice(data as DeviceRow);

  const { data: bubbleRow } = await supabase.from("bubbles").select("devices").eq("id", bubbleId).single();
  if (bubbleRow) {
    const ids = (bubbleRow.devices as string[] | null) ?? [];
    if (!ids.includes(device.id)) {
      await supabase.from("bubbles").update({ devices: [...ids, device.id] }).eq("id", bubbleId);
    }
  }

  return device;
}

export async function registerDeviceByToken(token: string): Promise<RegisteredDevice | null> {
  const code = token.trim().toUpperCase();
  if (!code) throw new Error("Enter your device token.");

  const { data, error } = await supabase.rpc("get_device_by_token", { p_token: code });

  if (error) {
    if (/PGRST202/i.test(error.message ?? "")) {
      throw new Error("Device registration is not configured. Run supabase/devices.sql in Supabase SQL Editor.");
    }
    throw new Error(formatDbError(error, "Could not verify token."));
  }

  const row = Array.isArray(data) ? data[0] : data;
  if (!row) return null;

  return {
    id: row.id as string,
    name: row.name as string,
    placement: row.placement as string,
    bubbleName: row.bubble_name as string,
  };
}

export async function setDeviceStatusByToken(token: string, status: Device["status"]) {
  const { error } = await supabase.rpc("set_device_status_by_token", {
    p_token: token.trim().toUpperCase(),
    p_status: status,
  });
  if (error && !/PGRST202/i.test(error.message ?? "")) {
    throw new Error(formatDbError(error, "Could not update device status."));
  }
}

export async function setDeviceStatus(deviceId: string, status: Device["status"]) {
  const { error } = await supabase.rpc("set_device_status", {
    p_device_id: deviceId,
    p_status: status,
  });
  if (error && !/PGRST202/i.test(error.message ?? "")) {
    throw new Error(formatDbError(error, "Could not update device status."));
  }
}

export async function saveRecording(deviceId: string, blob: Blob, durationMs: number) {
  const stamp = Date.now();
  const storagePath = `${deviceId}/${stamp}.webm`;

  const { error: uploadError } = await supabase.storage.from(BUCKET).upload(storagePath, blob, {
    contentType: "video/webm",
    upsert: true,
  });
  if (uploadError) throw new Error(uploadError.message);

  const { error: rowError } = await supabase.from("device_recordings").insert({
    device: deviceId,
    storage_path: storagePath,
    duration_ms: durationMs,
  });
  if (rowError) throw new Error(formatDbError(rowError, "Could not save recording."));
}

export async function uploadLiveChunk(deviceId: string, blob: Blob) {
  const path = liveFeedStoragePath(deviceId);
  const { error } = await supabase.storage.from(BUCKET).upload(path, blob, {
    contentType: "video/webm",
    upsert: true,
  });
  if (error) throw new Error(error.message);
}

export async function fetchDeviceRecordings(deviceId: string) {
  const { data, error } = await supabase
    .from("device_recordings")
    .select("id, device, storage_path, duration_ms, created_at")
    .eq("device", deviceId)
    .order("created_at", { ascending: false })
    .limit(20);

  if (error) throw new Error(formatDbError(error, "Could not load recordings."));

  return (data ?? []).map((row) => ({
    id: row.id as string,
    deviceId: row.device as string,
    storagePath: row.storage_path as string,
    publicUrl: publicStorageUrl(row.storage_path as string),
    durationMs: row.duration_ms as number | null,
    createdAt: row.created_at as string,
  })) satisfies DeviceRecording[];
}

export async function deleteRecording(recordingId: string, storagePath: string) {
  // Delete from storage first
  const { error: storageError } = await supabase.storage.from(BUCKET).remove([storagePath]);
  if (storageError) {
    console.error("Storage deletion error:", storageError);
    throw new Error(storageError.message || "Could not delete video file.");
  }

  // Delete from database
  const { error: dbError } = await supabase.from("device_recordings").delete().eq("id", recordingId);
  if (dbError) {
    console.error("Database deletion error:", dbError);
    throw new Error(formatDbError(dbError, "Could not delete recording from database."));
  }
}

export function contactShareLinks(contact: string, token: string, deviceName: string) {
  const trimmed = contact.trim();
  if (!trimmed) return {};

  const body = encodeURIComponent(
    `Register this phone as a Vault camera for "${deviceName}".\n\n1. Open the Vault app\n2. Choose "Register device with token"\n3. Enter this code: ${token}`,
  );
  const subject = encodeURIComponent(`Vault device code — ${deviceName}`);

  if (isEmail(trimmed)) {
    return { mailto: `mailto:${trimmed}?subject=${subject}&body=${body}` };
  }
  if (isPhone(trimmed)) {
    const digits = trimmed.replace(/[^\d+]/g, "");
    return { sms: `sms:${digits}?body=${body}` };
  }
  return {};
}
