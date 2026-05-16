import { useEffect, useState } from "react";
import { Lock, Shield, AlertTriangle, CheckCircle, Circle, Loader } from "lucide-react";
import type { GuardianEvent } from "@/hooks/use-guardian-events";

type Step = { step: number; label: string; status: "done" | "active" | "pending" };

type Props = {
  event: GuardianEvent;
  onDismiss: () => void;
};

const DEFAULT_SEQUENCE: Step[] = [
  { step: 1, label: "Threat detected",    status: "done" },
  { step: 2, label: "Guardian AI engaged", status: "done" },
  { step: 3, label: "Smart lock engaging", status: "active" },
  { step: 4, label: "Premises secured",    status: "pending" },
];

export function SmartLockSequence({ event, onDismiss }: Props) {
  const raw = event.metadata?.sequence as Step[] | undefined;
  const initialSteps = raw ?? DEFAULT_SEQUENCE;

  const [steps, setSteps] = useState<Step[]>(initialSteps);

  // Animate pending → active → done with 900ms delays
  useEffect(() => {
    let current = initialSteps.findIndex((s) => s.status === "active");
    if (current === -1) return;

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
      if (current < initialSteps.length - 1) {
        setTimeout(advance, 900);
      }
    };

    const t = setTimeout(advance, 900);
    return () => clearTimeout(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const message = event.metadata?.message as string | undefined;

  return (
    <div className="mt-4 overflow-hidden rounded-2xl border border-danger/40 bg-danger/5">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-danger/20 bg-danger/10 px-4 py-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-danger/20 text-danger">
          <Lock className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-danger">Smart Lock Engaged</p>
          {message && (
            <p className="mt-0.5 truncate text-xs text-danger/70">{message}</p>
          )}
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="shrink-0 text-xs text-muted-foreground hover:text-foreground"
        >
          Dismiss
        </button>
      </div>

      {/* Sequence */}
      <ul className="space-y-0 px-4 py-3">
        {steps.map((s) => (
          <li key={s.step} className="flex items-center gap-3 py-1.5">
            <StepIcon status={s.status} />
            <span
              className={`text-sm ${
                s.status === "done"
                  ? "text-foreground line-through opacity-60"
                  : s.status === "active"
                  ? "font-medium text-danger"
                  : "text-muted-foreground"
              }`}
            >
              {s.label}
            </span>
            {s.status === "active" && (
              <span className="ml-auto text-xs text-danger animate-pulse">in progress</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function StepIcon({ status }: { status: Step["status"] }) {
  if (status === "done") return <CheckCircle className="h-4 w-4 shrink-0 text-success" />;
  if (status === "active") return <Loader className="h-4 w-4 shrink-0 animate-spin text-danger" />;
  return <Circle className="h-4 w-4 shrink-0 text-muted-foreground/40" />;
}
