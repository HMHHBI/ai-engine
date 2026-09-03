import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { authActions } from "./auth-actions";
import { authApi } from "@/lib/api/auth";
import { userApi } from "@/lib/api/user";
import { useAuthStore } from "@/features/auth";
import type { User } from "@/types/api";

vi.mock("@/lib/api/auth", () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
    google: vi.fn(),
    forgotPassword: vi.fn(),
    resetPassword: vi.fn(),
  },
}));

vi.mock("@/lib/api/user", () => ({
  userApi: {
    getProfile: vi.fn(),
  },
}));

const mockUser: User = {
  id: 1,
  name: "John Doe",
  email: "john@example.com",
  is_active: true,
  picture: "https://example.com/avatar.png",
  created_at: "2026-01-01T00:00:00Z",
};

describe("authActions", () => {
  beforeEach(() => {
    useAuthStore.getState().logout();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("logs in, sets auth token, and fetches user profile", async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: "mock-token",
      token_type: "bearer",
    });
    vi.mocked(userApi.getProfile).mockResolvedValue(mockUser);

    await authActions.login({
      email: "john@example.com",
      password: "password123",
    });

    expect(authApi.login).toHaveBeenCalledWith({
      email: "john@example.com",
      password: "password123",
    });
    expect(useAuthStore.getState().token).toBe("mock-token");
    expect(useAuthStore.getState().user).toEqual(mockUser);
  });

  it("registers then automatically logs in the user", async () => {
    vi.mocked(authApi.register).mockResolvedValue(mockUser);
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: "reg-token",
      token_type: "bearer",
    });
    vi.mocked(userApi.getProfile).mockResolvedValue(mockUser);

    await authActions.register({
      name: "John Doe",
      email: "john@example.com",
      password: "password123",
    });

    expect(authApi.register).toHaveBeenCalledWith({
      name: "John Doe",
      email: "john@example.com",
      password: "password123",
    });
    expect(useAuthStore.getState().token).toBe("reg-token");
    expect(useAuthStore.getState().user).toEqual(mockUser);
  });

  it("authenticates via google with token payload", async () => {
    vi.mocked(authApi.google).mockResolvedValue({
      access_token: "google-token",
      token_type: "bearer",
    });
    vi.mocked(userApi.getProfile).mockResolvedValue(mockUser);

    await authActions.google("g-credential-xyz");

    expect(authApi.google).toHaveBeenCalledWith({
      token: "g-credential-xyz",
    });
    expect(useAuthStore.getState().token).toBe("google-token");
    expect(useAuthStore.getState().user).toEqual(mockUser);
  });

  it("logs out and clears state", () => {
    useAuthStore.getState().setAuth("active-token", mockUser);

    authActions.logout();

    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
  });
});