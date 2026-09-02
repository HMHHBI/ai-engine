import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { User } from "@/types/api";

interface AuthState {
  token: string | null;
  user: User | null;
  isHydrated: boolean;

  isAuthenticated: () => boolean;

  setAuth: (token: string, user?: User | null) => void;
  setUser: (user: User | null) => void;
  logout: () => void;
  setHydrated: (hydrated: boolean) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      isHydrated: false,

      isAuthenticated: () => Boolean(get().token),

      setAuth: (token, user = null) => {
        set({
          token,
          user,
        });

        if (typeof window !== "undefined") {
          localStorage.setItem("token", token);
        }
      },

      setUser: (user) => {
        set({ user });
      },

      logout: () => {
        set({
          token: null,
          user: null,
        });

        if (typeof window !== "undefined") {
          localStorage.removeItem("token");
        }
      },

      setHydrated: (hydrated) => {
        set({
          isHydrated: hydrated,
        });
      },
    }),
    {
      name: "ai-engine-auth",

      partialize: (state) => ({
        token: state.token,
        user: state.user,
      }),

      onRehydrateStorage: () => (state) => {
        if (state?.token && typeof window !== "undefined") {
          localStorage.setItem("token", state.token);
        }

        state?.setHydrated(true);
      },
    },
  ),
);