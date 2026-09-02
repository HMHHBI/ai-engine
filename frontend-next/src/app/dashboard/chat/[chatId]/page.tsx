"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";

import { AuthGuard } from "@/components/auth/auth-guard";
import { AppShell } from "@/components/layout/app-shell";
import { useChatStore } from "@/features/chat/store/chat-store";
import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";

interface ChatPageProps {
  params: Promise<{
    chatId: string;
  }>;
}

function ChatPageContent({ params }: ChatPageProps) {
  const { chatId: rawChatId } = use(params);
  const router = useRouter();
  const parsedId = Number.parseInt(rawChatId, 10);

  const activeChatId = useChatStore((state) => state.activeChatId);

  useEffect(() => {
    if (Number.isNaN(parsedId)) {
      router.replace("/dashboard");
      return;
    }

    if (activeChatId !== parsedId) {
      useChatStore.getState().setActiveChat(parsedId);
      // Agar messages pehle se loaded na hon to load karein
      const existing = useChatStore.getState().messagesByChat[parsedId];
      if (!existing) {
        void chatSessionActions.loadChat(parsedId).catch(() => {
          router.replace("/dashboard");
        });
      }
    }
  }, [parsedId, activeChatId, router]);

  return <AppShell />;
}

export default function ChatPage({ params }: ChatPageProps) {
  return (
    <AuthGuard>
      <ChatPageContent params={params} />
    </AuthGuard>
  );
}
