"use client";

import Link from "next/link";
import { useState } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { authActions } from "@/features/auth/actions/auth-actions";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setMessage("");
    setError("");

    if (!email.trim()) {
      setError("Email address is required.");
      return;
    }

    setLoading(true);

    try {
      const response = await authActions.forgotPassword(email.trim());
      setMessage(response);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to send reset email.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthCard
      title="Reset your password"
      description="Enter your email and we'll send you a password reset link."
      footer={
        <Link
          href="/login"
          className="font-medium text-foreground hover:underline"
        >
          Back to login
        </Link>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="email" className="mb-2 block text-sm font-medium">
            Email address
          </label>

          <input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@company.com"
            disabled={loading}
            className="h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/20 disabled:opacity-60"
          />
        </div>

        {message && (
          <p className="rounded-lg border border-border bg-secondary px-3 py-2 text-sm">
            {message}
          </p>
        )}

        {error && (
          <p
            role="alert"
            className="rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="h-11 w-full rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:pointer-events-none disabled:opacity-50"
        >
          {loading ? "Sending…" : "Send reset link"}
        </button>
      </form>
    </AuthCard>
  );
}
