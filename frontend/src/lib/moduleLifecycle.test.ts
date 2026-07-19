import { describe, expect, it } from "vitest";
import {
  filterModulesByLifecycle,
  safeReplacementRoute,
} from "./moduleLifecycle";
import type { ModuleLifecycleOverride } from "../stores/moduleLifecycle";

const modules = [
  { key: "ativo", path: "/ativo", status: "active" },
  { key: "knowledge-hub", path: "/knowledge-hub", status: "active" },
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
  it("remove módulos ocultos, desabilitados e rotas já consolidadas", () => {
    expect(
      filterModulesByLifecycle(modules, settings).map((item) => item.key),
    ).toEqual(["ativo"]);
  });

  it("não reabre no menu uma rota consolidada por configuração administrativa", () => {
    const override: Record<string, ModuleLifecycleOverride> = {
      "knowledge-hub": {
        module_key: "knowledge-hub",
        enabled: true,
        menu_visible: true,
        status: "active",
      },
    };
    expect(
      filterModulesByLifecycle(modules, override).map((item) => item.key),
    ).not.toContain("knowledge-hub");
  });

  it("aceita apenas rotas internas diferentes da rota atual", () => {
    expect(safeReplacementRoute("/antigo", "/novo?tab=1")).toBe("/novo?tab=1");
    expect(safeReplacementRoute("/antigo", "https://example.com")).toBeNull();
    expect(safeReplacementRoute("/antigo", "//example.com")).toBeNull();
    expect(safeReplacementRoute("/antigo", "/antigo")).toBeNull();
  });
});
