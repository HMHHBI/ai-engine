"use client";

import { useState } from "react";

import { AppHeader } from "@/components/layout/app-header";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { ChatArea } from "@/features/chat/components/chat-area";

export function AppShell() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  return (
    <div className="flex h-dvh overflow-hidden bg-background text-foreground">
      <AppSidebar
        collapsed={sidebarCollapsed}
        mobileOpen={mobileSidebarOpen}
        onToggleCollapse={() => setSidebarCollapsed((current) => !current)}
        onCloseMobile={() => setMobileSidebarOpen(false)}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <AppHeader
          onOpenMobileSidebar={() => setMobileSidebarOpen(true)}
          onToggleSidebar={() => setSidebarCollapsed((current) => !current)}
        />

        <ChatArea />
      </main>
    </div>
  );
}
