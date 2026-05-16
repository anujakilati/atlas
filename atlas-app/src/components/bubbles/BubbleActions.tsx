import { useState } from "react";
import { Plus, Users } from "lucide-react";
import type { BubbleType } from "@/lib/bubbles";
import { createBubble, joinBubbleByToken } from "@/lib/bubbles";
import { bubbleTypeConfig } from "@/components/bubbles/bubble-styles";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type BubbleActionsProps = {
  onCreated: () => void;
};

export function BubbleActions({ onCreated }: BubbleActionsProps) {
  const [createOpen, setCreateOpen] = useState(false);
  const [joinOpen, setJoinOpen] = useState(false);

  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="flex min-h-[120px] flex-col items-center justify-center gap-2 rounded-3xl border border-dashed border-gold/50 bg-card/60 p-4 text-center transition-colors hover:border-gold"
        >
          <span className="grid h-11 w-11 place-items-center rounded-2xl bg-gradient-gold text-gold-foreground shadow-gold">
            <Plus className="h-5 w-5" />
          </span>
          <span className="text-sm font-medium">Create bubble</span>
        </button>
        <button
          type="button"
          onClick={() => setJoinOpen(true)}
          className="flex min-h-[120px] flex-col items-center justify-center gap-2 rounded-3xl border border-dashed border-border bg-card/60 p-4 text-center transition-colors hover:border-foreground/30"
        >
          <span className="grid h-11 w-11 place-items-center rounded-2xl border border-border bg-background/50">
            <Users className="h-5 w-5" />
          </span>
          <span className="text-sm font-medium">Join bubble</span>
        </button>
      </div>

      <CreateBubbleDialog open={createOpen} onOpenChange={setCreateOpen} onSuccess={onCreated} />
      <JoinBubbleDialog open={joinOpen} onOpenChange={setJoinOpen} onSuccess={onCreated} />
    </>
  );
}

function CreateBubbleDialog({
  open,
  onOpenChange,
  onSuccess,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}) {
  const [name, setName] = useState("");
  const [type, setType] = useState<BubbleType>("house");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await createBubble(name, type);
      setName("");
      setType("house");
      onOpenChange(false);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create bubble.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="border-border bg-card sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl">Create a bubble</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="bubble-name">Name</Label>
            <Input
              id="bubble-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Maple Street Home"
              required
              className="h-11 rounded-xl border-border bg-background/50"
            />
          </div>
          <div className="space-y-2">
            <Label>Type</Label>
            <div className="grid grid-cols-3 gap-2">
              {(Object.keys(bubbleTypeConfig) as BubbleType[]).map((key) => {
                const config = bubbleTypeConfig[key];
                const Icon = config.icon;
                const selected = type === key;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setType(key)}
                    className={`flex flex-col items-center gap-2 rounded-2xl border p-3 transition-all ${
                      selected ? "border-gold ring-1 ring-gold" : "border-border bg-background/30"
                    }`}
                  >
                    <Icon className={`h-5 w-5 ${selected ? "text-gold" : "text-muted-foreground"}`} />
                    <span className="text-xs font-medium">{config.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          <button
            type="submit"
            disabled={loading}
            className="flex h-11 w-full items-center justify-center rounded-xl bg-gradient-gold text-sm font-medium text-gold-foreground disabled:opacity-60"
          >
            {loading ? "Creating…" : "Create bubble"}
          </button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function JoinBubbleDialog({
  open,
  onOpenChange,
  onSuccess,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}) {
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await joinBubbleByToken(code);
      setCode("");
      onOpenChange(false);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not join bubble.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="border-border bg-card sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl">Join a bubble</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="invite-code">Invite code</Label>
            <Input
              id="invite-code"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              placeholder="ABC123"
              required
              maxLength={8}
              className="h-11 rounded-xl border-border bg-background/50 text-center font-mono text-lg tracking-[0.3em] uppercase"
            />
            <p className="text-xs text-muted-foreground">
              Ask a bubble member for their invite code from Add member.
            </p>
          </div>
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          <button
            type="submit"
            disabled={loading}
            className="flex h-11 w-full items-center justify-center rounded-xl bg-gradient-gold text-sm font-medium text-gold-foreground disabled:opacity-60"
          >
            {loading ? "Joining…" : "Join bubble"}
          </button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
