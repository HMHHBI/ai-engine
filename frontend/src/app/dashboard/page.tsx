"use client";

import { useEffect } from "react";

import { AuthGuard } from "@/components/auth/auth-guard";
import { AppShell } from "@/components/layout/app-shell";
import { useChatStore } from "@/features/chat/store/chat-store";

function DashboardContent() {
  useEffect(() => {
    if (useChatStore.getState().activeChatId !== null) {
      useChatStore.getState().setActiveChat(null);
    }
  }, []);

  return <AppShell />;
}

export default function DashboardPage() {
  return (
    <AuthGuard>
      <DashboardContent />
    </AuthGuard>
  );
}
