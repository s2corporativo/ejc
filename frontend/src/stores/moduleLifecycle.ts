import { create } from "zustand";
import api from "../lib/api";

export type ModuleLifecycleStatus =
  "active" | "beta" | "hidden" | "legacy" | "disabled";

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
  liberarPorTimeout: () => void;
  upsertLocal: (setting: ModuleLifecycleOverride) => void;
  removeLocal: (moduleKey: string) => void;
};

/**
 * Teto de espera do lifecycle (ms). O axios de `lib/api.ts` não define timeout
 * global: sem este limite, um `GET /system-modules/settings` pendente para
 * sempre deixaria o gate (e toda a área staff) preso no spinner. Vale para a
 * própria requisição E como fallback do gate.
 */
export const MODULE_LIFECYCLE_TIMEOUT_MS = 8000;

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
        }>("/system-modules/settings", {
          timeout: MODULE_LIFECYCLE_TIMEOUT_MS,
        });
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
  // Fallback do gate: esgotado o teto de espera, segue com o manifesto local
  // (mesmo desfecho do catch acima). Idempotente — não mexe em `loading` nem
  // cancela o request em voo, então uma resposta tardia ainda aplica settings.
  liberarPorTimeout: () =>
    set((state) => (state.loaded ? state : { loaded: true })),
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
