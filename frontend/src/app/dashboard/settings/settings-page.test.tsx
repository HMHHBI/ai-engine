import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import SettingsPage from "./page";
import { userApi } from "@/lib/api/user";
import { useAuthStore } from "@/features/auth";
import type { User } from "@/types/api";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

vi.mock("next-themes", () => ({
  useTheme: () => ({
    theme: "system",
    setTheme: vi.fn(),
  }),
}));

vi.mock("@/lib/api/user", () => ({
  userApi: {
    getProfile: vi.fn(),
    updateProfile: vi.fn(),
  },
}));

describe("SettingsPage", () => {
  const mockUser: User = {
    id: 1,
    email: "test@example.com",
    name: "Test User",
    full_name: "Test User",
    profile_image: "/default-avatar.png",
    picture: "/default-avatar.png",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
  };

  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: mockUser });
    vi.mocked(userApi.getProfile).mockResolvedValue(mockUser);
  });

  it("renders profile settings with prefilled user information", async () => {
    render(<SettingsPage />);

    expect(screen.getByText("Loading profile…")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByDisplayValue("Test User")).toBeInTheDocument();
      expect(screen.getByDisplayValue("test@example.com")).toBeInTheDocument();
    });
  });

  it("switches to appearance tab and renders theme options", async () => {
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("Test User")).toBeInTheDocument();
    });

    const appearanceTab = screen.getByRole("button", { name: /appearance/i });
    fireEvent.click(appearanceTab);

    expect(screen.getByText("System")).toBeInTheDocument();
    expect(screen.getByText("Light")).toBeInTheDocument();
    expect(screen.getByText("Dark")).toBeInTheDocument();
  });
});
