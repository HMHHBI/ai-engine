import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppHeader } from "./app-header";
import { useChatStore } from "@/features/chat/store/chat-store";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";

vi.mock("@/features/chat/actions/chat-session-actions", () => ({
  chatSessionActions: {
    updatePersona: vi.fn(),
  },
}));

vi.mock("@/features/chat/components/rag-status-badge", () => ({
  RagStatusBadge: () => <div data-testid="rag-status-badge" />,
}));

vi.mock("@/features/chat/components/chat-settings-drawer", () => ({
  ChatSettingsDrawer: () => null,
}));

vi.mock("@/features/documents/components/DocumentWorkspace", () => ({
  DocumentWorkspace: () => null,
}));

describe("AppHeader", () => {
  const chatId = 42;

  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.getState().reset();
    useChatSessionStore.getState().reset();

    useChatStore.getState().setActiveChat(chatId);
    useChatSessionStore.setState({
      sessions: [
        {
          id: chatId,
          user_id: 1,
          title: "Climate Policy Review",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          attached_documents_count: 0,
          primary_document_title: null,
          message_count: 0,
          last_active_at: null,
          persona: "academic",
          custom_instructions: "Focus on methodology.",
        },
      ],
    });
  });

  it("renders active session title and persona selector", () => {
    render(
      <AppHeader
        onOpenMobileSidebar={vi.fn()}
        onToggleSidebar={vi.fn()}
      />,
    );

    expect(screen.getByText("Climate Policy Review")).toBeDefined();
    expect(screen.getByTestId("research-mode-selector")).toBeDefined();
    expect(screen.getByText("Academic")).toBeDefined();
  });

  it("opens menu and persists new persona through chatSessionActions", async () => {
    vi.mocked(chatSessionActions.updatePersona).mockResolvedValueOnce({
      id: chatId,
      user_id: 1,
      title: "Climate Policy Review",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      attached_documents_count: 0,
      primary_document_title: null,
      message_count: 0,
      last_active_at: null,
      persona: "legal",
      custom_instructions: "Focus on methodology.",
    });

    render(
      <AppHeader
        onOpenMobileSidebar={vi.fn()}
        onToggleSidebar={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("research-mode-selector"));
    expect(screen.getByRole("menu")).toBeDefined();

    const legalOption = screen.getByRole("menuitem", { name: "Legal" });
    fireEvent.click(legalOption);

    await waitFor(() => {
      expect(chatSessionActions.updatePersona).toHaveBeenCalledWith(
        chatId,
        "legal",
        "Focus on methodology.",
      );
    });
  });

  it("does not render persona selector when activeChatId is null", () => {
    useChatStore.getState().setActiveChat(null);

    render(
      <AppHeader
        onOpenMobileSidebar={vi.fn()}
        onToggleSidebar={vi.fn()}
      />,
    );

    expect(screen.queryByTestId("research-mode-selector")).toBeNull();
  });
});
