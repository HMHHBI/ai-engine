"use client";

import { useRef, useState } from "react";

import { AppHeader } from "@/components/layout/app-header";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { ChatArea } from "@/features/chat/components/chat-area";

export function AppShell() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
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

        <ChatArea />
      </main>
    </div>
  );
}
