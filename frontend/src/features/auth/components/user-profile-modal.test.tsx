import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UserProfileModal } from "./user-profile-modal";
import { useAuthStore } from "@/features/auth";
import { userApi } from "@/lib/api/user";
import type { User, UserUsage } from "@/types/api";

vi.mock("@/lib/api/user", () => ({
  userApi: {
    getProfile: vi.fn(),
    getUsage: vi.fn(),
    updateProfile: vi.fn(),
  },
}));

describe("UserProfileModal", () => {
  const mockUser: User = {
    id: 1,
    name: "Hassan Bin Imran",
    full_name: "Hassan Bin Imran",
    email: "hassan@example.com",
    is_active: true,
    created_at: "2026-01-01",
    picture: null,
    profile_image: "/default-avatar.png",
    plan: "STANDARD",
    limits: { image: 15, search: 30 },
  };

  const mockUsage: UserUsage = {
    plan: "STANDARD",
    image: { remaining: 15 },
    search: { remaining: 30 },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().setUser(mockUser);
  });

  it("renders user profile and quota numbers on open", async () => {
    vi.mocked(userApi.getUsage).mockResolvedValueOnce(mockUsage);

    render(<UserProfileModal open={true} onClose={vi.fn()} />);

    expect(screen.getByText("Account")).toBeDefined();
    expect(screen.getByText("Hassan Bin Imran")).toBeDefined();
    expect(screen.getByText("hassan@example.com")).toBeDefined();
    expect(screen.getByText("Standard")).toBeDefined();

    await waitFor(() => {
      expect(screen.getByText("15")).toBeDefined();
      expect(screen.getByText("30")).toBeDefined();
    });
  });

  it("handles usage API failure without faking zero quota", async () => {
    vi.mocked(userApi.getUsage).mockRejectedValueOnce(new Error("500 Server Error"));

    render(<UserProfileModal open={true} onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("Usage information is unavailable.")).toBeDefined();
      expect(screen.getByRole("alert")).toBeDefined();
    });
  });

  it("updates display name and refreshes user profile", async () => {
    const onClose = vi.fn();
    vi.mocked(userApi.getUsage).mockResolvedValueOnce(mockUsage);
    vi.mocked(userApi.updateProfile).mockResolvedValueOnce({
      message: "Profile updated successfully",
    });
    vi.mocked(userApi.getProfile).mockResolvedValueOnce({
      ...mockUser,
      full_name: "Hassan Updated",
      name: "Hassan Updated",
    });

    render(<UserProfileModal open={true} onClose={onClose} />);

    const input = screen.getByLabelText("Display name");
    fireEvent.change(input, { target: { value: "Hassan Updated" } });

    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => {
      expect(userApi.updateProfile).toHaveBeenCalled();
      expect(userApi.getProfile).toHaveBeenCalled();
      expect(useAuthStore.getState().user?.full_name).toBe("Hassan Updated");
      expect(onClose).toHaveBeenCalled();
    });
  });
  it("calls onClose when Escape key is pressed", () => {
    const onClose = vi.fn();
    render(<UserProfileModal open={true} onClose={onClose} />);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});