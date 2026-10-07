import { describe, expect, it, vi, beforeEach } from "vitest";
import { userApi } from "./user";
import { apiClient } from "./client";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
  },
}));

describe("userApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls /user/me for getProfile", async () => {
    const mockUser = {
      id: 1,
      email: "test@example.com",
      name: "Test User",
      is_active: true,
      created_at: "2026-01-01",
      full_name: "Test User",
      profile_image: "/avatar.png",
      plan: "FREE" as const,
      limits: { image: 5, search: 10 },
    };
    vi.mocked(apiClient.get).mockResolvedValueOnce(mockUser);

    const result = await userApi.getProfile();
    expect(apiClient.get).toHaveBeenCalledWith("/user/me");
    expect(result).toEqual(mockUser);
  });

  it("calls /user/usage for getUsage", async () => {
    const mockUsage = {
      plan: "FREE" as const,
      image: { remaining: 5 },
      search: { remaining: 10 },
    };
    vi.mocked(apiClient.get).mockResolvedValueOnce(mockUsage);

    const result = await userApi.getUsage();
    expect(apiClient.get).toHaveBeenCalledWith("/user/usage");
    expect(result).toEqual(mockUsage);
  });

  it("calls /user/update-profile for updateProfile", async () => {
    const formData = new FormData();
    formData.append("name", "New Name");
    vi.mocked(apiClient.put).mockResolvedValueOnce({
      message: "Profile updated",
    });

    const result = await userApi.updateProfile(formData);
    expect(apiClient.put).toHaveBeenCalledWith(
      "/user/update-profile",
      formData,
    );
    expect(result).toEqual({ message: "Profile updated" });
  });
});
