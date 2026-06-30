import { create } from "zustand";
import type { User } from "../types";

interface AuthState {
  user: User | null;
  setSession: (u: User) => void;
  loadUser: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  user: JSON.parse(localStorage.getItem("ejc_user") || "null"),
  setSession: (u) => set({ user: u }),
  loadUser: () =>
    set({ user: JSON.parse(localStorage.getItem("ejc_user") || "null") }),
}));
