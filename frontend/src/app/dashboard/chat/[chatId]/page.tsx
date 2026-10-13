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

  const parsedId = Number(rawChatId);

  useEffect(() => {
    if (!Number.isInteger(parsedId) || parsedId <= 0) {
      chatSessionActions.invalidateHydration();
      router.replace("/dashboard");
      return;
    }

    if (useChatStore.getState().activeChatId === parsedId) {
      return;
    }

    let isSubscribed = true;

    void chatSessionActions
      .hydrateSession(parsedId)
      .then((loaded) => {
        if (!loaded || !isSubscribed) {
          return;
        }
      })
      .catch(() => {
        if (isSubscribed) {
          router.replace("/dashboard");
        }
      });

    return () => {
      isSubscribed = false;
    };
  }, [parsedId, router]);

  return <AppShell />;
}

export default function ChatPage({ params }: ChatPageProps) {
  return (
    <AuthGuard>
      <ChatPageContent params={params} />
    </AuthGuard>
  );
}
