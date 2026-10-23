"use client";

import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ChangeEvent,
  type FormEvent,
} from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { ArrowLeft, Check, LoaderCircle, Monitor, Moon, Sun, UserRound } from "lucide-react";

import { useAuthStore } from "@/features/auth";
import { userApi } from "@/lib/api/user";
import { cn } from "@/lib/utils";

type SettingsTab = "profile" | "appearance";
type ThemeOption = "system" | "light" | "dark";

const themeOptions: {
  value: ThemeOption;
  label: string;
  description: string;
  icon: typeof Monitor;
}[] = [
  {
    value: "system",
    label: "System",
    description: "Follow your device's appearance setting.",
    icon: Monitor,
  },
  {
    value: "light",
    label: "Light",
    description: "Use a light interface.",
    icon: Sun,
  },
  {
    value: "dark",
    label: "Dark",
    description: "Use a dark interface.",
    icon: Moon,
  },
];

const emptySubscribe = () => () => {};

export default function SettingsPage() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const { theme, setTheme } = useTheme();

  // Pure client hydration check without triggering cascading setState in useEffect
  const mounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  const [tab, setTab] = useState<SettingsTab>("profile");
  const [name, setName] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadProfile() {
      try {
        const profile = await userApi.getProfile();

        if (cancelled) return;

        setUser(profile);
        setName(profile.full_name || profile.name || "");
      } catch {
        if (!cancelled) {
          setError("Unable to load your profile. Please refresh the page.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadProfile();

    return () => {
      cancelled = true;
    };
  }, [setUser]);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setError(null);
    setSuccess(null);

    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }

    if (!file) {
      setSelectedFile(null);
      setPreviewUrl(null);
      return;
    }

    if (!file.type.startsWith("image/")) {
      setError("Choose a valid image file.");
      event.target.value = "";
      setSelectedFile(null);
      setPreviewUrl(null);
      return;
    }

    if (file.size > 2 * 1024 * 1024) {
      setError("The profile image must be 2 MB or smaller.");
      event.target.value = "";
      setSelectedFile(null);
      setPreviewUrl(null);
      return;
    }

    setSelectedFile(file);
    setPreviewUrl(URL.createObjectURL(file));
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const normalizedName = name.trim();

    if (!normalizedName) {
      setError("Display name cannot be empty.");
      return;
    }

    if (normalizedName.length > 100) {
      setError("Display name must be 100 characters or fewer.");
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const formData = new FormData();
      formData.append("name", normalizedName);

      if (selectedFile) {
        formData.append("profile_img", selectedFile);
      }

      await userApi.updateProfile(formData);

      const refreshedProfile = await userApi.getProfile();
      setUser(refreshedProfile);
      setName(refreshedProfile.full_name || refreshedProfile.name || "");
      setSelectedFile(null);
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        setPreviewUrl(null);
      }

      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      setSuccess("Profile updated successfully.");
    } catch {
      setError("Unable to save your profile. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  const displayName = user?.full_name || user?.name || name || "User";
  const avatarUrl =
    previewUrl ||
    (user?.profile_image &&
    user.profile_image !== "/default-avatar.png"
      ? user.profile_image
      : null);

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
      <button
        type="button"
        onClick={() => router.push("/dashboard")}
        className="mb-6 inline-flex items-center gap-2 rounded-md text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <ArrowLeft className="size-4" />
        Back to chat
      </button>

      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">
          Settings
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Manage your profile and application preferences.
        </p>
      </header>

      <div className="grid gap-8 md:grid-cols-[220px_minmax(0,1fr)]">
        <nav
          aria-label="Settings sections"
          className="flex gap-2 overflow-x-auto md:flex-col"
        >
          <button
            type="button"
            onClick={() => setTab("profile")}
            aria-current={tab === "profile" ? "page" : undefined}
            className={cn(
              "flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors",
              tab === "profile"
                ? "bg-secondary font-medium text-foreground"
                : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
            )}
          >
            <UserRound className="size-4" />
            Profile
          </button>

          <button
            type="button"
            onClick={() => setTab("appearance")}
            aria-current={tab === "appearance" ? "page" : undefined}
            className={cn(
              "flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors",
              tab === "appearance"
                ? "bg-secondary font-medium text-foreground"
                : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
            )}
          >
            <Sun className="size-4" />
            Appearance
          </button>
        </nav>

        <section className="min-w-0">
          {tab === "profile" ? (
            <div className="rounded-xl border border-border bg-background">
              <div className="border-b border-border px-5 py-4 sm:px-6">
                <h2 className="font-semibold">Profile</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Update your display name and profile picture.
                </p>
              </div>

              {loading ? (
                <div className="flex items-center gap-2 px-6 py-10 text-sm text-muted-foreground">
                  <LoaderCircle className="size-4 animate-spin" />
                  Loading profile…
                </div>
              ) : (
                <form onSubmit={handleSave}>
                  <div className="space-y-6 px-5 py-6 sm:px-6">
                    <div>
                      <label className="mb-3 block text-sm font-medium">
                        Profile picture
                      </label>

                      <div className="flex flex-wrap items-center gap-4">
                        <div className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-full bg-secondary text-lg font-semibold">
                          {avatarUrl ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              src={avatarUrl}
                              alt="Profile preview"
                              className="size-full object-cover"
                            />
                          ) : (
                            displayName.charAt(0).toUpperCase()
                          )}
                        </div>

                        <div className="space-y-2">
                          <input
                            ref={fileInputRef}
                            type="file"
                            accept="image/*"
                            onChange={handleFileChange}
                            className="block max-w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border file:border-border file:bg-background file:px-3 file:py-2 file:text-sm file:font-medium file:text-foreground hover:file:bg-secondary"
                          />
                          <p className="text-xs text-muted-foreground">
                            Image file, maximum 2 MB. Changes are applied
                            when you save.
                          </p>
                        </div>
                      </div>
                    </div>

                    <div>
                      <label
                        htmlFor="settings-display-name"
                        className="mb-2 block text-sm font-medium"
                      >
                        Display name
                      </label>
                      <input
                        id="settings-display-name"
                        value={name}
                        onChange={(event) => setName(event.target.value)}
                        maxLength={100}
                        autoComplete="name"
                        required
                        className="h-10 w-full rounded-lg border border-border bg-background px-3 text-sm outline-none transition focus-visible:ring-2 focus-visible:ring-ring"
                      />
                    </div>

                    <div>
                      <label
                        htmlFor="settings-email"
                        className="mb-2 block text-sm font-medium"
                      >
                        Email address
                      </label>
                      <input
                        id="settings-email"
                        value={user?.email ?? ""}
                        readOnly
                        disabled
                        className="h-10 w-full cursor-not-allowed rounded-lg border border-border bg-secondary/40 px-3 text-sm text-muted-foreground"
                      />
                      <p className="mt-2 text-xs text-muted-foreground">
                        Email changes are not supported in the current
                        profile API.
                      </p>
                    </div>

                    {error && (
                      <p role="alert" className="text-sm text-destructive">
                        {error}
                      </p>
                    )}

                    {success && (
                      <p role="status" className="text-sm text-emerald-600">
                        {success}
                      </p>
                    )}
                  </div>

                  <div className="flex justify-end border-t border-border px-5 py-4 sm:px-6">
                    <button
                      type="submit"
                      disabled={saving || loading}
                      className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {saving && (
                        <LoaderCircle className="size-4 animate-spin" />
                      )}
                      {saving ? "Saving…" : "Save changes"}
                    </button>
                  </div>
                </form>
              )}
            </div>
          ) : (
            <div className="rounded-xl border border-border bg-background">
              <div className="border-b border-border px-5 py-4 sm:px-6">
                <h2 className="font-semibold">Appearance</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Choose how AI Engine looks on this device.
                </p>
              </div>

              <div className="space-y-3 p-5 sm:p-6">
                {themeOptions.map((option) => {
                  const Icon = option.icon;
                  const selected = mounted && theme === option.value;

                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setTheme(option.value)}
                      aria-pressed={selected}
                      className={cn(
                        "flex w-full items-center gap-4 rounded-xl border p-4 text-left transition-colors",
                        selected
                          ? "border-foreground/40 bg-secondary/50"
                          : "border-border hover:bg-secondary/40",
                      )}
                    >
                      <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-secondary">
                        <Icon className="size-5" />
                      </span>

                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium">
                          {option.label}
                        </span>
                        <span className="mt-1 block text-sm text-muted-foreground">
                          {option.description}
                        </span>
                      </span>

                      <span className="flex size-5 shrink-0 items-center justify-center rounded-full border border-border">
                        {selected && <Check className="size-3.5" />}
                      </span>
                    </button>
                  );
                })}

                {!mounted && (
                  <p className="text-xs text-muted-foreground">
                    Loading appearance preference…
                  </p>
                )}
              </div>
            </div>
          )}

          <div className="mt-6 rounded-xl border border-border bg-background p-5 sm:p-6">
            <h2 className="font-semibold">Account deletion</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Account deletion is not enabled yet. It will be available
              after the backend deletion workflow and storage cleanup
              have been implemented and tested.
            </p>
            <button
              type="button"
              disabled
              className="mt-4 h-9 cursor-not-allowed rounded-lg border border-destructive/40 px-3 text-sm font-medium text-destructive opacity-50"
              title="Account deletion is not implemented yet"
            >
              Delete account — unavailable
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}
