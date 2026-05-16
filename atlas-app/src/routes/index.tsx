import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { LayoutGrid } from "lucide-react";
import { useAuth } from "@/contexts/auth-context";
import { signOut } from "@/lib/auth";
import { fetchMyBubbles, type Bubble } from "@/lib/bubbles";
import { BubbleActions } from "@/components/bubbles/BubbleActions";
import { BubbleTile } from "@/components/bubbles/BubbleTile";

export const Route = createFileRoute("/")({
  component: DashboardPage,
  head: () => ({
    meta: [{ title: "Vault — Your bubbles" }],
  }),
});

function DashboardPage() {
  const { session, profile, refreshProfile } = useAuth();
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const metaName = session?.user.user_metadata?.name as string | undefined;
  const displayName = profile?.username?.split(" ")[0] ?? metaName?.split(" ")[0] ?? "there";

  const loadBubbles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await refreshProfile();
      setBubbles(await fetchMyBubbles());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load bubbles.");
    } finally {
      setLoading(false);
    }
  }, [refreshProfile]);

  useEffect(() => {
    void loadBubbles();
  }, [loadBubbles]);

  return (
    <div className="px-5 pt-12 pb-8">
      <header className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Your spaces</p>
          <h1 className="mt-1 font-display text-3xl leading-none">
            Hi, <span className="italic text-gold">{displayName}</span>
          </h1>
          <p className="mt-2 max-w-xs text-sm text-muted-foreground">
            Pick a bubble to open its vault, or create / join one to get started.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void signOut()}
          className="shrink-0 rounded-full border border-border bg-card px-3 py-2 text-xs text-muted-foreground"
        >
          Log out
        </button>
      </header>

      <section className="mt-8">
        <div className="mb-4 flex items-center gap-2">
          <LayoutGrid className="h-4 w-4 text-gold" />
          <h2 className="font-display text-2xl">Bubbles</h2>
        </div>

        {error ? (
          <p className="mb-4 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">{error}</p>
        ) : null}

        {loading ? (
          <p className="text-sm text-muted-foreground">Loading your bubbles…</p>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {bubbles.map((bubble) => (
              <BubbleTile key={bubble.id} bubble={bubble} />
            ))}
            <BubbleActions onCreated={loadBubbles} />
          </div>
        )}

        {!loading && bubbles.length === 0 && !error ? (
          <p className="mt-4 text-center text-sm text-muted-foreground">
            No bubbles yet — create one for your home, store, or school.
          </p>
        ) : null}
      </section>
    </div>
  );
}
