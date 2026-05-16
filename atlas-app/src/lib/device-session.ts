const STORAGE_KEY = "vault_device_session";

export type DeviceSession = {
  deviceId: string;
  token: string;
  name: string;
  placement: string;
  bubbleName: string;
};

export function getDeviceSession(): DeviceSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as DeviceSession;
  } catch {
    return null;
  }
}

export function setDeviceSession(session: DeviceSession) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearDeviceSession() {
  localStorage.removeItem(STORAGE_KEY);
}
