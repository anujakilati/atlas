import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Smartphone, LogIn } from "lucide-react";
import { useEffect, useState } from "react";
import { registerDeviceByToken } from "@/lib/devices";
import { getDeviceSession, setDeviceSession } from "@/lib/device-session";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const Route = createFileRoute("/device/")({
  component: DeviceRegisterPage,
  head: () => ({
    meta: [{ title: "Vault — Register device" }],
  }),
});

function DeviceRegisterPage() {
  const navigate = useNavigate();
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const session = getDeviceSession();
    if (session) {
      void navigate({ to: "/device/live", replace: true });
    }
  }, [navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const device = await registerDeviceByToken(token);
      if (!device) {
        setError("Invalid device token. Check the code from your bubble owner.");
        return;
      }
      const code = token.trim().toUpperCase();
      setDeviceSession({
        deviceId: device.id,
        token: code,
        name: device.name,
        placement: device.placement,
        bubbleName: device.bubbleName,
      });
      await navigate({ to: "/device/live" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not register device.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col px-5 pb-8 pt-14">
      <header className="text-center">
        <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Vault camera</p>
        <h1 className="mt-2 font-display text-3xl">Register this device</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Enter the device token from your bubble owner. This phone will only stream video — no account needed.
        </p>
      </header>

      <form onSubmit={(e) => void handleSubmit(e)} className="mt-10 space-y-4">
        <div className="space-y-2">
          <Label htmlFor="device-token">Device token</Label>
          <Input
            id="device-token"
            value={token}
            onChange={(e) => setToken(e.target.value.toUpperCase())}
            placeholder="e.g. K7M2XP9A"
            className="rounded-xl border-border bg-card text-center font-mono text-lg tracking-[0.2em]"
            autoComplete="off"
            required
          />
        </div>

        {error ? <p className="text-sm text-danger">{error}</p> : null}

        <button
          type="submit"
          disabled={loading}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-gold py-3.5 text-sm font-medium text-gold-foreground disabled:opacity-60"
        >
          <Smartphone className="h-4 w-4" />
          {loading ? "Verifying…" : "Register & start camera"}
        </button>
      </form>

      <div className="mt-10 rounded-2xl border border-border bg-card/60 p-4">
        <p className="text-xs uppercase tracking-wider text-muted-foreground">Bubble members</p>
        <p className="mt-1 text-sm text-muted-foreground">
          To manage locks, bubbles, and live view — sign in with your account.
        </p>
        <Link
          to="/login"
          className="mt-3 inline-flex items-center gap-2 text-sm font-medium text-gold"
        >
          <LogIn className="h-4 w-4" />
          Sign in
        </Link>
      </div>
    </div>
  );
}
