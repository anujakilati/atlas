import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { AuthCard } from "@/components/auth/AuthCard";
import { formatAuthError, signUp } from "@/lib/auth";

export const Route = createFileRoute("/signup")({
  component: SignUpPage,
  head: () => ({ meta: [{ title: "Vault — Sign up" }] }),
});

function SignUpPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const { session } = await signUp(email, password, name);
      if (session) {
        await navigate({ to: "/" });
      } else {
        setSuccess("Account created. Check your email to confirm, then log in.");
      }
    } catch (err) {
      setError(formatAuthError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthCard
      title="Create your vault"
      subtitle="Sign up with your name, email, and password."
      fields={[
        { id: "name", label: "Name", type: "text", autoComplete: "name", value: name, onChange: setName },
        { id: "email", label: "Email", type: "email", autoComplete: "email", value: email, onChange: setEmail },
        {
          id: "password",
          label: "Password",
          type: "password",
          autoComplete: "new-password",
          value: password,
          onChange: setPassword,
        },
      ]}
      submitLabel="Create account"
      loading={loading}
      error={error}
      success={success}
      onSubmit={handleSubmit}
      footer={
        <div className="space-y-3">
          <p>
            Already have an account?{" "}
            <Link to="/login" className="font-medium text-gold">
              Log in
            </Link>
          </p>
          <p>
            Camera device?{" "}
            <Link to="/device" className="font-medium text-gold">
              Register with token
            </Link>
          </p>
        </div>
      }
    />
  );
}
