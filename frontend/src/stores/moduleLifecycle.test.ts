import { describe, it, expect, beforeEach, vi } from "vitest";

const get = vi.fn();
vi.mock("../lib/api", () => ({
  default: { get: (...a: unknown[]) => get(...a) },
}));

import {
  MODULE_LIFECYCLE_TIMEOUT_MS,
  useModuleLifecycleStore,
} from "./moduleLifecycle";

const reset = () =>
  useModuleLifecycleStore.setState({
    settings: {},
    protectedKeys: [],
    loaded: false,
    loading: false,
  });

describe("stores/moduleLifecycle", () => {
  beforeEach(() => {
    get.mockReset();
    reset();
  });

  it("aplica o teto de espera na própria requisição (axios sem timeout global)", async () => {
    get.mockResolvedValue({ data: { data: [], protected_module_keys: [] } });
    await useModuleLifecycleStore.getState().load();
    expect(get).toHaveBeenCalledWith("/system-modules/settings", {
      timeout: MODULE_LIFECYCLE_TIMEOUT_MS,
    });
    expect(useModuleLifecycleStore.getState().loaded).toBe(true);
  });

  it("fail-open: erro de rede termina carregado com o manifesto local", async () => {
    get.mockRejectedValue(new Error("timeout of 8000ms exceeded"));
    await useModuleLifecycleStore.getState().load();
    const s = useModuleLifecycleStore.getState();
    expect(s.loaded).toBe(true);
    expect(s.settings).toEqual({});
  });

  it("liberarPorTimeout marca carregado sem apagar settings e é idempotente", () => {
    const { liberarPorTimeout } = useModuleLifecycleStore.getState();
    liberarPorTimeout();
    expect(useModuleLifecycleStore.getState().loaded).toBe(true);
    const antes = useModuleLifecycleStore.getState();
    liberarPorTimeout();
    // Mesma referência de estado: nenhum re-render/loop no gate.
    expect(useModuleLifecycleStore.getState()).toBe(antes);
  });

  it("resposta tardia após o fallback ainda aplica os overrides", async () => {
    useModuleLifecycleStore.getState().liberarPorTimeout();
    get.mockResolvedValue({
      data: {
        data: [
          {
            module_key: "casos",
            enabled: false,
            menu_visible: false,
            status: "disabled",
          },
        ],
        protected_module_keys: ["dashboard"],
      },
    });
    await useModuleLifecycleStore.getState().load();
    const s = useModuleLifecycleStore.getState();
    expect(s.settings.casos?.enabled).toBe(false);
    expect(s.protectedKeys).toEqual(["dashboard"]);
  });
});
