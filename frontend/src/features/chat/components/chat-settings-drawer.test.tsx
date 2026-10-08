import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatSettingsDrawer } from "./chat-settings-drawer";
import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";
import { chatApi } from "@/lib/api/chat";
import type { ChatSession } from "@/types/api";

vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    getDetails: vi.fn(),
  },
}));

vi.mock("@/features/chat/actions/chat-session-actions", () => ({
  chatSessionActions: {
    updatePersona: vi.fn(),
  },
}));

const mockAcademicSession: ChatSession = {
  id: 42,
  user_id: 1,
  title: "Session 42",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  persona: "academic",
  custom_instructions: "Explain rigorously.",
  attached_documents_count: 0,
  primary_document_title: null,
  message_count: 0,
  last_active_at: null,
};

const mockDeveloperSession: ChatSession = {
  ...mockAcademicSession,
  persona: "developer",
  custom_instructions: "Code only",
};

describe("ChatSettingsDrawer", () => {
  const chatId = 42;

  beforeEach(() => {
    vi.clearAllMocks();
    useChatSessionStore.getState().reset();
    useChatSessionStore.setState({
      sessions: [mockAcademicSession],
    });
  });

  it("renders five personas and loads existing settings from store without calling getDetails", () => {
    render(
      <ChatSettingsDrawer chatId={chatId} open={true} onClose={vi.fn()} />,
    );

    expect(chatApi.getDetails).not.toHaveBeenCalled();

    const radioAcademic = screen.getByDisplayValue(
      "academic",
    ) as HTMLInputElement;
    expect(radioAcademic.checked).toBe(true);
    expect(screen.getByDisplayValue("Explain rigorously.")).toBeDefined();
    expect(screen.getAllByRole("radio")).toHaveLength(5);
  });

  it("calls updatePersona and closes on save", async () => {
    const onClose = vi.fn();
    vi.mocked(chatSessionActions.updatePersona).mockResolvedValueOnce(
      mockDeveloperSession,
    );

    render(
      <ChatSettingsDrawer chatId={chatId} open={true} onClose={onClose} />,
    );

    const developerRadio = screen.getByDisplayValue("developer");
    fireEvent.click(developerRadio);

    const textarea = screen.getByPlaceholderText(/tell the assistant/i);
    fireEvent.change(textarea, { target: { value: "Code only" } });

    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(chatSessionActions.updatePersona).toHaveBeenCalledWith(
        chatId,
        "developer",
        "Code only",
      );
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("shows error alert when updatePersona fails", async () => {
    vi.mocked(chatSessionActions.updatePersona).mockRejectedValueOnce(
      new Error("Network error"),
    );

    render(
      <ChatSettingsDrawer chatId={chatId} open={true} onClose={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeDefined();
      expect(screen.getByText("Unable to save chat settings.")).toBeDefined();
    });
  });
  it("calls onClose when Escape key is pressed", () => {
    const onClose = vi.fn();
    render(<ChatSettingsDrawer chatId={chatId} open={true} onClose={onClose} />);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});