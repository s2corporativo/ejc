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

  it("no catálogo (/ferramentas) o status oculto do manifesto não esconde nada", () => {
    // O hub existe justamente para os módulos tirados do menu; filtrar por
    // `status: "hidden"` ali esvaziaria a tela inteira.
    const ocultosNoManifesto = [
      { key: "prompts", path: "/prompts", status: "hidden" },
      { key: "radar", path: "/radar", status: "hidden" },
    ];
    expect(
      filterModulesByLifecycle(ocultosNoManifesto, {}, "catalogo").map(
        (item) => item.key,
      ),
    ).toEqual(["prompts", "radar"]);
  });

  it("no catálogo, remove o módulo desligado pela administração", () => {
    const catalogo = [
      { key: "oculto", path: "/oculto", status: "hidden" },
      { key: "desabilitado", path: "/desabilitado", status: "hidden" },
    ];
    // `oculto` tem menu_visible:false, mas continua acessível pelo gate — o
    // hub deve oferecê-lo. `desabilitado` levaria à tela de indisponível.
    expect(
      filterModulesByLifecycle(catalogo, settings, "catalogo").map(
        (item) => item.key,
      ),
    ).toEqual(["oculto"]);
  });

  it("aceita apenas rotas internas diferentes da rota atual", () => {
    expect(safeReplacementRoute("/antigo", "/novo?tab=1")).toBe("/novo?tab=1");
    expect(safeReplacementRoute("/antigo", "https://example.com")).toBeNull();
    expect(safeReplacementRoute("/antigo", "//example.com")).toBeNull();
    expect(safeReplacementRoute("/antigo", "/antigo")).toBeNull();
  });
});
