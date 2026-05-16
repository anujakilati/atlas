import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { AuthCard } from "@/components/auth/AuthCard";
import { signIn } from "@/lib/auth";

export const Route = createFileRoute("/login")({
  component: LoginPage,
  head: () => ({ meta: [{ title: "Vault — Log in" }] }),
});

function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await signIn(email, password);
      await navigate({ to: "/" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not log in.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthCard
      title="Welcome back"
      subtitle="Log in to control your home."
      fields={[
        {
          id: "email",
          label: "Email",
          type: "email",
          autoComplete: "email",
          value: email,
          onChange: setEmail,
        },
        {
          id: "password",
          label: "Password",
          type: "password",
          autoComplete: "current-password",
          value: password,
          onChange: setPassword,
        },
      ]}
      submitLabel="Log in"
      loading={loading}
      error={error}
      onSubmit={handleSubmit}
      footer={
        <>
          New here?{" "}
          <Link to="/signup" className="font-medium text-gold">
            Create an account
          </Link>
        </>
      }
    />
  );
}
