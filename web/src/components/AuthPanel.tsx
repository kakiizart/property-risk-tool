"use client";

import { useState } from "react";

import { useAuth } from "@/lib/auth";

/**
 * Compact email/password auth card. Renders nothing when Supabase auth is not
 * configured, a skeleton while the session resolves, a signed-in bar, or the
 * sign-in / sign-up form.
 */
export default function AuthPanel() {
  const { enabled, loading, user, signIn, signUp, signOut } = useAuth();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (!enabled) return null;

  if (loading) {
    return (
      <div
        className="h-10 w-full animate-pulse rounded-md bg-slate-100"
        aria-label="Loading account"
      />
    );
  }

  if (user) {
    return (
      <div className="flex items-center justify-between rounded-md border border-slate-200 bg-white px-4 py-2.5 text-sm">
        <span className="text-slate-600">
          Signed in as <span className="font-medium text-slate-900">{user.email}</span>
        </span>
        <button
          type="button"
          onClick={() => void signOut()}
          className="font-medium text-slate-600 hover:text-slate-900"
        >
          Sign out
        </button>
      </div>
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      if (mode === "signin") {
        await signIn(email, password);
      } else {
        const { needsConfirmation } = await signUp(email, password);
        if (needsConfirmation) {
          setNotice("Account created. Check your email to confirm, then sign in.");
          setMode("signin");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-md border border-slate-200 bg-white p-4"
      aria-label={mode === "signin" ? "Sign in" : "Create account"}
    >
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900">
          {mode === "signin" ? "Sign in to save reports" : "Create an account"}
        </h2>
        <button
          type="button"
          onClick={() => {
            setMode(mode === "signin" ? "signup" : "signin");
            setError(null);
            setNotice(null);
          }}
          className="text-xs font-medium text-slate-500 hover:text-slate-900"
        >
          {mode === "signin" ? "Need an account?" : "Have an account?"}
        </button>
      </div>

      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          type="email"
          required
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
        />
        <input
          type="password"
          required
          minLength={6}
          autoComplete={mode === "signin" ? "current-password" : "new-password"}
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
        >
          {busy ? "…" : mode === "signin" ? "Sign in" : "Sign up"}
        </button>
      </div>

      {error && (
        <p role="alert" className="mt-2 text-sm text-red-700">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="mt-2 text-sm text-emerald-700">
          {notice}
        </p>
      )}
    </form>
  );
}
