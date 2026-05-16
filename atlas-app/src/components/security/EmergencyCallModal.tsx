import { useEffect, useState } from "react";
import { Phone, CheckCircle, Circle, Loader, X } from "lucide-react";
import type { GuardianEvent } from "@/hooks/use-guardian-events";

type Step = { step: number; label: string; status: "done" | "active" | "pending" };

type Props = {
  event: GuardianEvent;
  onDismiss: () => void;
};

const DEFAULT_SEQUENCE: Step[] = [
  { step: 1, label: "Emergency detected",     status: "done" },
  { step: 2, label: "Contacting authorities", status: "active" },
  { step: 3, label: "Call request sent",      status: "pending" },
];

export function EmergencyCallModal({ event, onDismiss }: Props) {
  const raw = event.metadata?.sequence as Step[] | undefined;
  const initialSteps = raw ?? DEFAULT_SEQUENCE;

  const [steps, setSteps] = useState<Step[]>(initialSteps);
  const [callConnected, setCallConnected] = useState(false);

  // Animate sequence, then mark as connected
  useEffect(() => {
    let current = initialSteps.findIndex((s) => s.status === "active");
    if (current === -1) current = 1;

    const advance = () => {
      setSteps((prev) => {
        const next = prev.map((s, i) => {
          if (i === current) return { ...s, status: "done" as const };
          if (i === current + 1) return { ...s, status: "active" as const };
          return s;
        });
        return next;
      });
      current += 1;
      if (current < initialSteps.length) {
        setTimeout(advance, 1200);
      } else {
        setTimeout(() => setCallConnected(true), 600);
      }
    };

    const t = setTimeout(advance, 1200);
    return () => clearTimeout(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-dismiss after 45s
  useEffect(() => {
    const t = setTimeout(onDismiss, 45_000);
    return () => clearTimeout(t);
  }, [onDismiss]);

  const message = event.metadata?.message as string | undefined;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-4 sm:items-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onDismiss}
      />

      {/* Modal */}
      <div className="relative w-full max-w-sm overflow-hidden rounded-3xl border border-danger/50 bg-background shadow-2xl">
        {/* Dismiss */}
        <button
          type="button"
          onClick={onDismiss}
          className="absolute right-4 top-4 z-10 grid h-8 w-8 place-items-center rounded-full bg-muted text-muted-foreground hover:bg-muted/80"
          aria-label="Dismiss"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Alert band */}
        <div className="bg-danger px-5 py-4 text-danger-foreground">
          <p className="text-xs font-semibold uppercase tracking-widest opacity-80">
            Guardian AI — Critical Alert
          </p>
          <h2 className="mt-1 font-display text-2xl">Emergency Call</h2>
        </div>

        <div className="px-5 py-5">
          {/* Phone animation */}
          <div className="flex flex-col items-center py-4">
            <div
              className={`relative grid h-20 w-20 place-items-center rounded-full ${
                callConnected ? "bg-success/20" : "bg-danger/10"
              }`}
            >
              {!callConnected && (
                <span className="absolute inset-0 animate-ping rounded-full bg-danger/20" />
              )}
              <Phone
                className={`h-8 w-8 ${callConnected ? "text-success" : "text-danger animate-pulse"}`}
              />
            </div>
            <p className="mt-3 font-display text-3xl tracking-widest text-danger">911</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {callConnected ? "Call request sent to authorities" : "Initiating emergency call…"}
            </p>
          </div>

          {/* Description */}
          {message && (
            <p className="mb-4 rounded-xl bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
              {message}
            </p>
          )}

          {/* Sequence */}
          <ul className="space-y-2">
            {steps.map((s) => (
              <li key={s.step} className="flex items-center gap-3">
                <StepIcon status={s.status} />
                <span
                  className={`flex-1 text-sm ${
                    s.status === "done"
                      ? "text-muted-foreground line-through"
                      : s.status === "active"
                      ? "font-medium text-foreground"
                      : "text-muted-foreground/50"
                  }`}
                >
                  {s.label}
                </span>
              </li>
            ))}
          </ul>

          <p className="mt-4 text-center text-xs text-muted-foreground">
            This is a simulated emergency alert — no real call has been placed.
          </p>

          <button
            type="button"
            onClick={onDismiss}
            className="mt-4 w-full rounded-2xl border border-border bg-card py-3 text-sm font-medium text-foreground hover:bg-accent"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}

function StepIcon({ status }: { status: Step["status"] }) {
  if (status === "done") return <CheckCircle className="h-4 w-4 shrink-0 text-success" />;
  if (status === "active") return <Loader className="h-4 w-4 shrink-0 animate-spin text-danger" />;
  return <Circle className="h-4 w-4 shrink-0 text-muted-foreground/30" />;
}
