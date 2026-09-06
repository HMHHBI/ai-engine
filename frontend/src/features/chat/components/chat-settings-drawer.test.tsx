import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatSettingsDrawer } from "@/features/chat/components/chat-settings-drawer";
import { chatSessionActions } from "@/features/chat/actions/chat-session-actions";
import { chatApi } from "@/lib/api/chat";

vi.mock("@/lib/api/chat", () => ({
  chatApi: {
    getDetails: vi.fn(),
    updatePersona: vi.fn(),
  },
}));

const mockedChatApi = vi.mocked(chatApi);

describe("ChatSettingsDrawer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders five personas and loads existing settings", async () => {
    mockedChatApi.getDetails.mockResolvedValueOnce({
      id: 42,
      title: "Test Chat",
      pdf_context: null,
      ai_provider: null,
      ai_model: null,
      embedding_provider: null,
      persona: "academic",
      custom_instructions: "Explain rigorously.",
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
      messages: [],
      has_pdf: false,
    });

    render(<ChatSettingsDrawer chatId={42} open={true} onClose={vi.fn()} />);

    await waitFor(() => {
      const radioAcademic = screen.getByDisplayValue(
        "academic",
      ) as HTMLInputElement;
      expect(radioAcademic.checked).toBe(true);
      expect(screen.getByDisplayValue("Explain rigorously.")).toBeDefined();
    });

    expect(screen.getAllByRole("radio")).toHaveLength(5);
  });

  it("calls updatePersona and closes on save", async () => {
    mockedChatApi.getDetails.mockResolvedValueOnce({
      id: 42,
      title: "Test Chat",
      pdf_context: null,
      ai_provider: null,
      ai_model: null,
      embedding_provider: null,
      persona: "default",
      custom_instructions: null,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
      messages: [],
      has_pdf: false,
    });

    const updateSpy = vi
      .spyOn(chatSessionActions, "updatePersona")
      .mockResolvedValueOnce({} as never);

    const onClose = vi.fn();

    render(<ChatSettingsDrawer chatId={42} open={true} onClose={onClose} />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /save changes/i }),
      ).toBeDefined();
    });

    fireEvent.click(screen.getByRole("radio", { name: /developer/i }));

    const textarea = screen.getByPlaceholderText(/tell the assistant/i);
    fireEvent.change(textarea, { target: { value: "Code only" } });

    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(42, "developer", "Code only");
      expect(onClose).toHaveBeenCalled();
    });
  });
});
