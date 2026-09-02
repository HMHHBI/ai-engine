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

export interface LoginResponse extends AuthTokens {
  user?: Partial<User>;
}

export interface GoogleAuthResponse extends AuthTokens {
  user?: Partial<User>;
}

export interface MessageResponse {
  message: string;
}

export const authApi = {
  register(payload: RegisterPayload): Promise<User> {
    return apiClient.post<User>("/auth/signup", payload, {
      skipAuth: true,
    });
  },

  login(payload: LoginPayload): Promise<LoginResponse> {
    return apiClient.post<LoginResponse>("/auth/login", payload, {
      skipAuth: true,
    });
  },

  google(payload: GoogleAuthPayload): Promise<GoogleAuthResponse> {
    return apiClient.post<GoogleAuthResponse>("/auth/google", payload, {
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