"use client";

import { Suspense, useRef, useState, useEffect } from "react";

import { AppHeader } from "@/components/layout/app-header";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { WorkspaceSkeleton } from "@/features/workspace/components/workspace-skeleton";
import { WorkspaceController } from "@/features/workspace/components/workspace-controller";

export function AppShell() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  useEffect(() => {
    function handleGlobalKeyDown(event: KeyboardEvent) {
      const modifier = event.metaKey || event.ctrlKey;
      if (!modifier || event.altKey) {
        return;
      }

      if (event.key.toLowerCase() === "b") {
        event.preventDefault();
        setSidebarCollapsed((current) => !current);
        return;
      }

      if (event.key.toLowerCase() === "k") {
        event.preventDefault();
        const composer = document.querySelector<HTMLTextAreaElement>(
          '[data-chat-composer="true"]',
        );
        composer?.focus();
      }
    }

    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => {
      window.removeEventListener("keydown", handleGlobalKeyDown);
    };
  }, []);

  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  function handleOpenMobileSidebar() {
    setMobileSidebarOpen(true);
  }

  function handleCloseMobileSidebar() {
    setMobileSidebarOpen(false);
    // Return focus to the trigger button that opened the drawer
    triggerRef.current?.focus();
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-background text-foreground">
      <AppSidebar
        collapsed={sidebarCollapsed}
        mobileOpen={mobileSidebarOpen}
        onToggleCollapse={() => setSidebarCollapsed((current) => !current)}
        onCloseMobile={handleCloseMobileSidebar}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <AppHeader
          ref={triggerRef}
          onOpenMobileSidebar={handleOpenMobileSidebar}
          onToggleSidebar={() => setSidebarCollapsed((current) => !current)}
        />

        <Suspense fallback={<WorkspaceSkeleton />}>
          <WorkspaceController />
        </Suspense>
      </main>
    </div>
  );
}
