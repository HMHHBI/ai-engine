import { apiClient } from "@/lib/api/client";
import type {
  AuthTokens,
  GoogleAuthPayload,
  User,
} from "@/types/api";

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface ForgotPasswordPayload {
  email: string;
}

export interface ResetPasswordPayload {
  token: string;
  new_password: string;
}

export interface AuthResponse extends AuthTokens {
  user?: User;
}

export interface MessageResponse {
  message: string;
}

export const authApi = {
  register(payload: RegisterPayload): Promise<AuthResponse> {
    return apiClient.post<AuthResponse>("/auth/signup", payload, {
      skipAuth: true,
    });
  },

  login(payload: LoginPayload): Promise<AuthResponse> {
    return apiClient.post<AuthResponse>("/auth/login", payload, {
      skipAuth: true,
    });
  },

  google(payload: GoogleAuthPayload): Promise<AuthResponse> {
    return apiClient.post<AuthResponse>("/auth/google", payload, {
      skipAuth: true,
    });
  },

  forgotPassword(
    payload: ForgotPasswordPayload,
  ): Promise<MessageResponse> {
    return apiClient.post<MessageResponse>(
      "/auth/forgot-password",
      payload,
      {
        skipAuth: true,
      },
    );
  },

  resetPassword(
    payload: ResetPasswordPayload,
  ): Promise<MessageResponse> {
    return apiClient.post<MessageResponse>(
      "/auth/reset-password",
      payload,
      {
        skipAuth: true,
      },
    );
  },
};