import { create } from "zustand";
import api from "../lib/api";

export type ModuleLifecycleStatus =
  | "active"
  | "beta"
  | "hidden"
  | "legacy"
  | "disabled";

export type ModuleLifecycleOverride = {
  module_key: string;
  enabled: boolean;
  menu_visible: boolean;
  status: ModuleLifecycleStatus;
  replacement_route?: string | null;
  removal_date?: string | null;
  reason?: string | null;
  updated_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

type ModuleLifecycleState = {
  settings: Record<string, ModuleLifecycleOverride>;
  protectedKeys: string[];
  loaded: boolean;
  loading: boolean;
  load: () => Promise<void>;
  upsertLocal: (setting: ModuleLifecycleOverride) => void;
  removeLocal: (moduleKey: string) => void;
};

let inFlight: Promise<void> | null = null;

export const useModuleLifecycleStore = create<ModuleLifecycleState>((set) => ({
  settings: {},
  protectedKeys: [],
  loaded: false,
  loading: false,
  load: async () => {
    if (inFlight) return inFlight;
    inFlight = (async () => {
      set({ loading: true });
      try {
        const { data } = await api.get<{
          data: ModuleLifecycleOverride[];
          protected_module_keys: string[];
        }>("/system-modules/settings");
        set({
          settings: Object.fromEntries(
            (data.data ?? []).map((setting) => [setting.module_key, setting]),
          ),
          protectedKeys: data.protected_module_keys ?? [],
          loaded: true,
        });
      } catch {
        // Feature flags são operacionais, não autorização. Falha de carregamento
        // mantém o manifesto local disponível (fail-open controlado).
        set({ loaded: true });
      } finally {
        set({ loading: false });
        inFlight = null;
      }
    })();
    return inFlight;
  },
  upsertLocal: (setting) =>
    set((state) => ({
      settings: { ...state.settings, [setting.module_key]: setting },
    })),
  removeLocal: (moduleKey) =>
    set((state) => {
      const next = { ...state.settings };
      delete next[moduleKey];
      return { settings: next };
    }),
}));
