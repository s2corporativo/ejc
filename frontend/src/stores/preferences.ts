import { create } from "zustand";
import { persist } from "zustand/middleware";

export type HomeRoute =
  | "/"
  | "/atividades"
  | "/casos"
  | "/clientes"
  | "/inteligencia"
  | "/financeiro";

interface PreferencesState {
  homeRoute: HomeRoute;
  sidebarCollapsed: boolean;
  setHomeRoute: (route: HomeRoute) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
}

export const usePreferencesStore = create<PreferencesState>()(
  persist(
    (set) => ({
      homeRoute: "/",
      sidebarCollapsed: false,
      setHomeRoute: (homeRoute) => set({ homeRoute }),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
    }),
    {
      name: "ejc_preferences",
      version: 1,
      partialize: (state) => ({
        homeRoute: state.homeRoute,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
    },
  ),
);
