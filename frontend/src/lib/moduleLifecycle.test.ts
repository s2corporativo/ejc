import { describe, expect, it } from "vitest";
import {
  filterModulesByLifecycle,
  safeReplacementRoute,
} from "./moduleLifecycle";
import type { ModuleLifecycleOverride } from "../stores/moduleLifecycle";

const modules = [
  { key: "ativo", path: "/ativo", status: "active" },
  { key: "oculto", path: "/oculto", status: "active" },
  { key: "desabilitado", path: "/desabilitado", status: "active" },
];

const settings: Record<string, ModuleLifecycleOverride> = {
  oculto: {
    module_key: "oculto",
    enabled: true,
    menu_visible: false,
    status: "hidden",
  },
  desabilitado: {
    module_key: "desabilitado",
    enabled: false,
    menu_visible: false,
    status: "disabled",
    replacement_route: "/ativo",
  },
};

describe("moduleLifecycle", () => {
  it("remove módulos ocultos e desabilitados da navegação", () => {
    expect(filterModulesByLifecycle(modules, settings).map((item) => item.key)).toEqual([
      "ativo",
    ]);
  });

  it("aceita apenas rotas internas diferentes da rota atual", () => {
    expect(safeReplacementRoute("/antigo", "/novo?tab=1")).toBe(
      "/novo?tab=1",
    );
    expect(safeReplacementRoute("/antigo", "https://example.com")).toBeNull();
    expect(safeReplacementRoute("/antigo", "//example.com")).toBeNull();
    expect(safeReplacementRoute("/antigo", "/antigo")).toBeNull();
  });
});
