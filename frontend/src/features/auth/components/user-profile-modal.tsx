"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";

import { useAuthStore } from "@/features/auth";
import { userApi } from "@/lib/api/user";
import type { UserUsage } from "@/types/api";

interface UserProfileModalProps {
  open: boolean;
  onClose: () => void;
}

const PLAN_LABELS = {
  FREE: "Free",
  STANDARD: "Standard",
  PRO: "Pro",
} as const;

export function UserProfileModal({
  open,
  onClose,
}: UserProfileModalProps) {
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);

  const [name, setName] = useState(() => user?.full_name || user?.name || "");
  const [prevUser, setPrevUser] = useState(user);
  const [usage, setUsage] = useState<UserUsage | null>(null);
  const [loadingUsage, setLoadingUsage] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync draft state with user prop changes
  if (user !== prevUser) {
    setPrevUser(user);
    setName(user?.full_name || user?.name || "");
  }

  useEffect(() => {
    if (!open) {
      return;
    }

    let cancelled = false;

    async function fetchUsage() {
      setLoadingUsage(true);
      try {
        const response = await userApi.getUsage();
        if (!cancelled) {
          setUsage(response);
        }
      } catch {
        if (!cancelled) {
          setError("Unable to load usage information.");
        }
      } finally {
        if (!cancelled) {
          setLoadingUsage(false);
        }
      }
    }

    void fetchUsage();

    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !saving) {
        onClose();
      }
    }

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, onClose, saving]);

  async function handleSave() {
    const normalizedName = name.trim();

    if (!normalizedName) {
      setError("Name cannot be empty.");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("name", normalizedName);

      await userApi.updateProfile(formData);

      setLoadingProfile(true);

      const refreshedUser = await userApi.getProfile();
      setUser(refreshedUser);

      onClose();
    } catch {
      setError("Unable to update your profile.");
    } finally {
      setLoadingProfile(false);
      setSaving(false);
    }
  }

  if (!open || !user) {
    return null;
  }

  const displayName = user.full_name || user.name || "User";
  const userPlan = user.plan || "FREE";

  return (
    <div className="fixed inset-0 z-[60]">
      <button
        type="button"
        aria-label="Close account"
        className="absolute inset-0 bg-black/40 backdrop-blur-xs"
        onClick={() => {
          if (!saving) {
            onClose();
          }
        }}
      />

      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="account-title"
        className="absolute left-1/2 top-1/2 w-[min(92vw,32rem)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-xl border border-border bg-background shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h2
              id="account-title"
              className="text-base font-semibold"
            >
              Account
            </h2>

            <p className="text-xs text-muted-foreground">
              Profile, plan, and research quota.
            </p>
          </div>

          <button
            type="button"
            aria-label="Close account"
            disabled={saving}
            onClick={onClose}
            className="rounded-md p-2 hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="space-y-6 p-5">
          <section className="flex items-center gap-3">
            <div className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-full bg-secondary text-sm font-semibold">
              {user.profile_image &&
              user.profile_image !== "/default-avatar.png" ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={user.profile_image}
                  alt=""
                  className="size-full object-cover"
                />
              ) : (
                displayName.charAt(0).toUpperCase()
              )}
            </div>

            <div className="min-w-0">
              <p className="truncate font-medium">
                {displayName}
              </p>
              <p className="truncate text-sm text-muted-foreground">
                {user.email}
              </p>
            </div>
          </section>

          <section className="rounded-lg border border-border p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">
                  Current plan
                </p>
                <p className="mt-1 text-sm font-semibold">
                  {PLAN_LABELS[userPlan]}
                </p>
              </div>

              <span className="rounded-full border border-border px-2.5 py-1 text-xs font-medium">
                {userPlan}
              </span>
            </div>
          </section>

          <section>
            <div className="mb-3">
              <h3 className="text-sm font-semibold">
                Usage & quota
              </h3>

              <p className="mt-1 text-xs text-muted-foreground">
                Remaining usage from the current account limits.
              </p>
            </div>

            {loadingUsage ? (
              <div className="space-y-2">
                <div className="h-16 animate-pulse rounded-lg bg-secondary" />
                <div className="h-16 animate-pulse rounded-lg bg-secondary" />
              </div>
            ) : usage ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-border p-4">
                  <p className="text-xs text-muted-foreground">
                    Image generation
                  </p>

                  <p className="mt-2 text-2xl font-semibold">
                    {usage.image.remaining}
                  </p>

                  <p className="text-xs text-muted-foreground">
                    remaining
                  </p>
                </div>

                <div className="rounded-lg border border-border p-4">
                  <p className="text-xs text-muted-foreground">
                    Search
                  </p>

                  <p className="mt-2 text-2xl font-semibold">
                    {usage.search.remaining}
                  </p>

                  <p className="text-xs text-muted-foreground">
                    remaining
                  </p>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Usage information is unavailable.
              </p>
            )}
          </section>

          <section className="space-y-2">
            <label
              htmlFor="account-name"
              className="text-sm font-medium"
            >
              Display name
            </label>

            <input
              id="account-name"
              value={name}
              disabled={saving}
              onChange={(event) => setName(event.target.value)}
              className="h-10 w-full rounded-lg border border-border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            />
          </section>

          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-border p-4">
          <button
            type="button"
            disabled={saving}
            onClick={onClose}
            className="rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            Close
          </button>

          <button
            type="button"
            disabled={saving || loadingProfile}
            onClick={() => void handleSave()}
            className="rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            {saving ? "Saving..." : "Save profile"}
          </button>
        </div>
      </div>
    </div>
  );
}
