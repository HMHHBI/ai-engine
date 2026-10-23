import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import SettingsPage from "./page";
import { userApi } from "@/lib/api/user";
import { useAuthStore } from "@/features/auth";
import type { User } from "@/types/api";

const mockSetTheme = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

vi.mock("next-themes", () => ({
  useTheme: () => ({
    theme: "system",
    setTheme: mockSetTheme,
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

  it("updates display name and submits form with FormData", async () => {
    vi.mocked(userApi.updateProfile).mockResolvedValueOnce({
      ...mockUser,
      name: "Updated Name",
      full_name: "Updated Name",
    });

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("Test User")).toBeInTheDocument();
    });

    const nameInput = screen.getByLabelText(/display name/i);
    fireEvent.change(nameInput, { target: { value: "Updated Name" } });

    const submitBtn = screen.getByRole("button", { name: /save changes/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(userApi.updateProfile).toHaveBeenCalledTimes(1);
    });

    const calledArg = vi.mocked(userApi.updateProfile).mock.calls[0][0];
    expect(calledArg).toBeInstanceOf(FormData);
    expect(calledArg.get("name")).toBe("Updated Name");
  });

  it("displays error message if update profile API fails", async () => {
    vi.mocked(userApi.updateProfile).mockRejectedValueOnce(new Error("Network Error"));

    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("Test User")).toBeInTheDocument();
    });

    const submitBtn = screen.getByRole("button", { name: /save changes/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Unable to save your profile. Please try again.");
    });
  });

  it("switches to appearance tab and triggers setTheme for options", async () => {
    render(<SettingsPage />);

    await waitFor(() => {
      expect(screen.getByDisplayValue("Test User")).toBeInTheDocument();
    });

    const appearanceTab = screen.getByRole("button", { name: /appearance/i });
    fireEvent.click(appearanceTab);

    const darkBtn = screen.getByRole("button", { name: /dark/i });
    fireEvent.click(darkBtn);
    expect(mockSetTheme).toHaveBeenCalledWith("dark");

    const lightBtn = screen.getByRole("button", { name: /light/i });
    fireEvent.click(lightBtn);
    expect(mockSetTheme).toHaveBeenCalledWith("light");

    const systemBtn = screen.getByRole("button", { name: /system/i });
    fireEvent.click(systemBtn);
    expect(mockSetTheme).toHaveBeenCalledWith("system");
  });
});
