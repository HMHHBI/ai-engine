import { authApi } from "@/lib/api/auth";
import { userApi } from "@/lib/api/user";
import { useAuthStore } from "@/features/auth";
import type { LoginPayload, RegisterPayload } from "@/lib/api/auth";

export const authActions = {
  async login(payload: LoginPayload): Promise<void> {
    const response = await authApi.login(payload);

    if (!response.access_token) {
      throw new Error("Authentication failed.");
    }

    useAuthStore.getState().setAuth(response.access_token);

    const user = await userApi.getProfile();

    useAuthStore.getState().setUser(user);
  },

  async register(payload: RegisterPayload): Promise<void> {
    await authApi.register(payload);

    await this.login({
      email: payload.email,
      password: payload.password,
    });
  },

  async google(credential: string): Promise<void> {
    const response = await authApi.google({
      token: credential,
    });

    if (!response.access_token) {
      throw new Error("Google authentication failed.");
    }

    useAuthStore.getState().setAuth(response.access_token);

    const user = await userApi.getProfile();

    useAuthStore.getState().setUser(user);
  },

  async forgotPassword(email: string): Promise<string> {
    const response = await authApi.forgotPassword({
      email,
    });

    return response.message;
  },

  async resetPassword(
    token: string,
    newPassword: string,
  ): Promise<string> {
    const response = await authApi.resetPassword({
      token,
      new_password: newPassword,
    });

    return response.message;
  },

  logout(): void {
    useAuthStore.getState().logout();
  },
};