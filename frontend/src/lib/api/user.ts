import { apiClient } from "@/lib/api/client";
import type { User } from "@/types/api";

export interface UpdateProfileResponse {
  message?: string;
  user?: User;
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
};
