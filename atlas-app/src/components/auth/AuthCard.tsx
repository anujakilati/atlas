import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type AuthField = {
  id: string;
  label: string;
  type: string;
  autoComplete?: string;
  value: string;
  onChange: (value: string) => void;
};

type AuthCardProps = {
  title: string;
  subtitle: string;
  fields: AuthField[];
  submitLabel: string;
  loading?: boolean;
  error?: string | null;
  success?: string | null;
  footer: React.ReactNode;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
};

export function AuthCard({
  title,
  subtitle,
  fields,
  submitLabel,
  loading,
  error,
  success,
  footer,
  onSubmit,
}: AuthCardProps) {
  return (
    <div className="relative flex min-h-screen flex-col justify-center px-5 py-12">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[320px] bg-gradient-glow" />
      <div className="relative mx-auto w-full max-w-sm">
        <p className="font-display text-3xl italic text-gold">Vault</p>
        <h1 className="mt-8 font-display text-4xl leading-tight">{title}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{subtitle}</p>

        <form onSubmit={onSubmit} className="mt-8 space-y-4">
          {fields.map((field) => (
            <div key={field.id} className="space-y-2">
              <Label htmlFor={field.id}>{field.label}</Label>
              <Input
                id={field.id}
                type={field.type}
                autoComplete={field.autoComplete}
                value={field.value}
                onChange={(e) => field.onChange(e.target.value)}
                required
                className="h-12 rounded-xl border-border bg-card/80 px-4"
              />
            </div>
          ))}

          {error ? (
            <p className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">{error}</p>
          ) : null}
          {success ? (
            <p className="rounded-xl border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">{success}</p>
          ) : null}

          <button
            type="submit"
            disabled={loading}
            className="mt-2 flex h-12 w-full items-center justify-center rounded-xl bg-gradient-gold text-sm font-medium text-gold-foreground shadow-gold transition-opacity disabled:opacity-60"
          >
            {loading ? "Please wait…" : submitLabel}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-muted-foreground">{footer}</p>
      </div>
    </div>
  );
}
