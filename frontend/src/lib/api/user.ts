import { apiClient } from "@/lib/api/client";
import type { User } from "@/types/api";

export interface UpdateProfileResponse {
  message?: string;
  user?: User;
}

export interface UpgradeRequestResponse {
  message: string;
}

export const userApi = {
  getProfile(): Promise<User> {
    return apiClient.get<User>("/user/me");
  },

  updateProfile(
    formData: FormData,
  ): Promise<UpdateProfileResponse> {
    return apiClient.put<UpdateProfileResponse>(
      "/user/update-profile",
      formData,
    );
  },

  requestUpgrade(): Promise<UpgradeRequestResponse> {
    return apiClient.post<UpgradeRequestResponse>(
      "/user/upgrade-plan",
    );
  },
};