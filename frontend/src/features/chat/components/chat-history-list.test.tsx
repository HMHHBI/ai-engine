import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatHistoryList } from "./chat-history-list";
import { useChatSessionStore } from "@/features/chat/store/chat-session-store";

vi.mock("next/navigation", () => ({
  useParams: () => ({ chatId: "1" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/dashboard",
}));

describe("ChatHistoryList", () => {
  it("renders loading skeletons before sessions are available", () => {
    useChatSessionStore.setState({
      isLoading: true,
      sessions: [],
      error: null,
    });

    render(<ChatHistoryList />);

    expect(screen.queryByText("No research sessions yet")).not.toBeInTheDocument();
    expect(document.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0);
  });
});
