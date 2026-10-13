"use client";

import { useEffect, useSyncExternalStore } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useAuthStore } from "@/features/auth";

interface AuthGuardProps {
  children: React.ReactNode;
}

const emptySubscribe = () => () => {};

export function AuthGuard({ children }: AuthGuardProps) {
  const router = useRouter();
  const pathname = usePathname();

  const token = useAuthStore((state) => state.token);

  const isHydrated = useAuthStore((state) => state.isHydrated);

  const mounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  useEffect(() => {
    // Fallback if zustand rehydrate callback delayed on empty storage
    if (mounted && !isHydrated && !token) {
      const timer = setTimeout(() => {
        useAuthStore.getState().setHydrated(true);
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [mounted, isHydrated, token]);

  useEffect(() => {
    if (!mounted || !isHydrated || token) {
      return;
    }

    const next = encodeURIComponent(pathname);

    router.replace(`/login?next=${next}`);
  }, [mounted, isHydrated, token, pathname, router]);

  if (!mounted || !isHydrated || !token) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-background">
        <div className="text-sm text-muted-foreground">Loading...</div>
      </div>
    );
  }

  return <>{children}</>;
}
