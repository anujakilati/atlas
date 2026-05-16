import { useEffect, useState } from "react";
import { Copy, Check, RefreshCw } from "lucide-react";
import { getBubbleInviteToken } from "@/lib/bubbles";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type AddMemberDialogProps = {
  bubbleId: string;
  bubbleName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function AddMemberDialog({ bubbleId, bubbleName, open, onOpenChange }: AddMemberDialogProps) {
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const loadToken = async (regenerate = false) => {
    setLoading(true);
    setError(null);
    setCopied(false);
    try {
      const code = await getBubbleInviteToken(bubbleId, regenerate);
      setToken(code);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load invite code.");
      setToken(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) void loadToken(false);
  }, [open, bubbleId]);

  const copyToken = async () => {
    if (!token) return;
    await navigator.clipboard.writeText(token);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="border-border bg-card sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl">Add member</DialogTitle>
          <DialogDescription className="sr-only">
            Share an invite code so others can join this bubble.
          </DialogDescription>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Share this code so others can join <span className="text-foreground">{bubbleName}</span>.
        </p>

        <div className="mt-4 rounded-2xl border border-border bg-background/50 p-5 text-center">
          {loading ? (
            <p className="text-sm text-muted-foreground">Generating code…</p>
          ) : token ? (
            <p className="font-mono text-3xl font-medium tracking-[0.35em] text-gold">{token}</p>
          ) : (
            <p className="text-sm text-danger">{error ?? "No code available"}</p>
          )}
        </div>

        {error && token ? <p className="mt-2 text-sm text-danger">{error}</p> : null}

        <div className="mt-5 flex gap-2">
          <button
            type="button"
            onClick={() => void copyToken()}
            disabled={!token || loading}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-gradient-gold py-3 text-sm font-medium text-gold-foreground disabled:opacity-60"
          >
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copied ? "Copied" : "Copy code"}
          </button>
          <button
            type="button"
            onClick={() => void loadToken(true)}
            disabled={loading}
            className="grid h-12 w-12 place-items-center rounded-xl border border-border bg-card text-muted-foreground"
            aria-label="Generate new code"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
