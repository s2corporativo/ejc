import { create } from "zustand";
import type { User } from "../types";

interface AuthState {
  user: User | null;
  setSession: (u: User) => void;
  loadUser: () => void;
  /** Mescla campos no usuário atual (ex.: avatar_url) e persiste. */
  updateUser: (patch: Partial<User>) => void;
}

export const useAuth = create<AuthState>((set) => ({
  user: JSON.parse(localStorage.getItem("ejc_user") || "null"),
  setSession: (u) => set({ user: u }),
  loadUser: () =>
    set({ user: JSON.parse(localStorage.getItem("ejc_user") || "null") }),
  updateUser: (patch) =>
    set((state) => {
      if (!state.user) return state;
      const next = { ...state.user, ...patch };
      try {
        localStorage.setItem("ejc_user", JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return { user: next };
    }),
}));
