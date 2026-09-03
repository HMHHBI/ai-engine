"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { GoogleSignIn } from "@/components/auth/google-sign-in";
import { authActions } from "@/features/auth/actions/auth-actions";
import { ApiError } from "@/lib/errors/api-error";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setError("");

    if (!email.trim() || !password) {
      setError("Email and password are required.");
      return;
    }

    setLoading(true);

    try {
      await authActions.login({
        email: email.trim(),
        password,
      });

      const next = searchParams.get("next");

      router.replace(next && next.startsWith("/") ? next : "/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Unable to sign in.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthCard
      title="Welcome back"
      description="Sign in to continue your conversations."
      footer={
        <p>
          Don&apos;t have an account?{" "}
          <Link
            href="/signup"
            className="font-medium text-foreground hover:underline"
          >
            Create one
          </Link>
        </p>
      }
    >
      <div className="space-y-5">
        <GoogleSignIn
          onSuccess={async (credential) => {
            setError("");
            setLoading(true);

            try {
              await authActions.google(credential);
              router.replace("/dashboard");
            } catch (err) {
              setError(
                err instanceof Error
                  ? err.message
                  : "Google authentication failed.",
              );
            } finally {
              setLoading(false);
            }
          }}
          disabled={loading}
        />

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-border" />
          </div>

          <div className="relative flex justify-center">
            <span className="bg-card px-3 text-xs text-muted-foreground">
              OR
            </span>
          </div>
        </div>

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
              className="h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none transition focus:border-ring focus:ring-2 focus:ring-ring/20 disabled:opacity-60"
            />
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <label htmlFor="password" className="text-sm font-medium">
                Password
              </label>

              <Link
                href="/forgot-password"
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Forgot password?
              </Link>
            </div>

            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              disabled={loading}
              className="h-11 w-full rounded-xl border border-border bg-background px-3 text-sm outline-none transition focus:border-ring focus:ring-2 focus:ring-ring/20 disabled:opacity-60"
            />
          </div>

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
            className="h-11 w-full rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:pointer-events-none disabled:opacity-50"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </AuthCard>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-dvh items-center justify-center bg-background">
          <span className="text-sm text-muted-foreground">Loading…</span>
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
