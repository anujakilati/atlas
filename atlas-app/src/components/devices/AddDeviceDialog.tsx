import { useState } from "react";
import { Copy, Check, Mail, MessageSquare } from "lucide-react";
import {
  createDevice,
  contactShareLinks,
  PLACEMENT_OPTIONS,
  type Device,
} from "@/lib/devices";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type AddDeviceDialogProps = {
  bubbleId: string;
  bubbleName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeviceAdded?: (device: Device) => void;
};

export function AddDeviceDialog({
  bubbleId,
  bubbleName,
  open,
  onOpenChange,
  onDeviceAdded,
}: AddDeviceDialogProps) {
  const [name, setName] = useState("");
  const [placement, setPlacement] = useState<string>(PLACEMENT_OPTIONS[0]);
  const [customPlacement, setCustomPlacement] = useState("");
  const [contact, setContact] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Device | null>(null);
  const [copied, setCopied] = useState(false);

  const reset = () => {
    setName("");
    setPlacement(PLACEMENT_OPTIONS[0]);
    setCustomPlacement("");
    setContact("");
    setError(null);
    setCreated(null);
    setCopied(false);
    setLoading(false);
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  const resolvedPlacement = placement === "Other" ? customPlacement.trim() : placement;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const device = await createDevice(bubbleId, {
        name,
        placement: resolvedPlacement,
        contact: contact || undefined,
      });
      setCreated(device);
      onDeviceAdded?.(device);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add device.");
    } finally {
      setLoading(false);
    }
  };

  const share = created ? contactShareLinks(created.contact, created.deviceToken, created.name) : {};

  const copyToken = async () => {
    if (!created) return;
    await navigator.clipboard.writeText(created.deviceToken);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="border-border bg-card sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl">
            {created ? "Device token" : "Add device"}
          </DialogTitle>
          <DialogDescription className="sr-only">
            {created
              ? "Copy the device token for the camera app."
              : "Register a new camera device for this bubble."}
          </DialogDescription>
        </DialogHeader>

        {!created ? (
          <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Add a camera to <span className="text-foreground">{bubbleName}</span>. We&apos;ll generate a
              token — the person installs the app and chooses <strong className="text-foreground">Register device with token</strong>.
            </p>

            <Field label="Device name" htmlFor="device-name">
              <Input
                id="device-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Front porch cam"
                className="rounded-xl border-border bg-background/50"
                required
              />
            </Field>

            <Field label="Placement" htmlFor="placement">
              <Select value={placement} onValueChange={setPlacement}>
                <SelectTrigger id="placement" className="rounded-xl border-border bg-background/50">
                  <SelectValue placeholder="Where is it?" />
                </SelectTrigger>
                <SelectContent>
                  {PLACEMENT_OPTIONS.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>

            {placement === "Other" ? (
              <Field label="Custom placement" htmlFor="custom-placement">
                <Input
                  id="custom-placement"
                  value={customPlacement}
                  onChange={(e) => setCustomPlacement(e.target.value)}
                  placeholder="e.g. Side gate"
                  className="rounded-xl border-border bg-background/50"
                  required
                />
              </Field>
            ) : null}

            <Field label="Email or phone (optional)" htmlFor="contact">
              <Input
                id="contact"
                value={contact}
                onChange={(e) => setContact(e.target.value)}
                placeholder="Send them the token"
                className="rounded-xl border-border bg-background/50"
              />
            </Field>

            {error ? <p className="text-sm text-danger">{error}</p> : null}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-gradient-gold py-3 text-sm font-medium text-gold-foreground disabled:opacity-60"
            >
              {loading ? "Creating…" : "Generate device token"}
            </button>
          </form>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              On the phone, open Vault → <span className="text-foreground">Register device with token</span> →
              enter this code. That device can only live stream — no vault access.
            </p>

            <div className="rounded-2xl border border-border bg-background/50 p-6 text-center">
              <p className="font-mono text-3xl font-medium tracking-[0.35em] text-gold">{created.deviceToken}</p>
            </div>

            <div className="flex flex-col gap-2">
              <button
                type="button"
                onClick={() => void copyToken()}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-gold py-3 text-sm font-medium text-gold-foreground"
              >
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                {copied ? "Copied" : "Copy token"}
              </button>

              {share.mailto ? (
                <a
                  href={share.mailto}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-border py-3 text-sm font-medium"
                >
                  <Mail className="h-4 w-4" />
                  Send email
                </a>
              ) : null}

              {share.sms ? (
                <a
                  href={share.sms}
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-border py-3 text-sm font-medium"
                >
                  <MessageSquare className="h-4 w-4" />
                  Send text message
                </a>
              ) : null}

              <button
                type="button"
                onClick={() => handleOpenChange(false)}
                className="w-full py-2 text-sm text-muted-foreground"
              >
                Done
              </button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}
