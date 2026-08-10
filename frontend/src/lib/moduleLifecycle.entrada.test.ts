import { describe, expect, it } from "vitest";
import { canRoleAccessPath } from "../config/moduleRegistry";
import { filterModulesByLifecycle, lifecycleForPath } from "./moduleLifecycle";
import type { ModuleLifecycleOverride } from "../stores/moduleLifecycle";

type ModuloTeste = {
  key: string;
  path: string;
  label: string;
  essential?: boolean;
};

const entrada: ModuloTeste = {
  key: "entrada",
  path: "/entrada",
  label: "Entrada de Caso",
  essential: false,
};
const sala: ModuloTeste = {
  key: "sala-juridica",
  path: "/sala-juridica",
  label: "Sala Jurídica",
  essential: true,
};
const raioX: ModuloTeste = {
  key: "raio-x-processo",
  path: "/raio-x",
  label: "Raio-X de Documentos",
};

function override(
  moduleKey: string,
  enabled: boolean,
): ModuleLifecycleOverride {
  return {
    module_key: moduleKey,
    enabled,
    menu_visible: enabled,
    status: enabled ? "active" : "disabled",
    reason: enabled ? null : "Desabilitado para manutenção",
  } as ModuleLifecycleOverride;
}

describe("Entrada Única — consolidação segura de navegação", () => {
  it("consolida Sala/Raio-X quando a Entrada já está disponível ao papel", () => {
    const result = filterModulesByLifecycle([entrada, sala, raioX], {});

    expect(result.map((item) => item.key)).toEqual(["entrada"]);
    expect(result[0]?.label).toBe("Entrada Única");
    expect(result[0]?.essential).toBe(true);
  });

  it("preserva Sala/Raio-X para papéis cujo RBAC não inclui /entrada", () => {
    const result = filterModulesByLifecycle([sala, raioX], {});

    expect(result.map((item) => item.key)).toEqual([
      "sala-juridica",
      "raio-x-processo",
    ]);
  });

  it("não esconde Sala/Raio-X quando a própria Entrada foi desabilitada", () => {
    const result = filterModulesByLifecycle([entrada, sala, raioX], {
      entrada: override("entrada", false),
    });

    expect(result.map((item) => item.key)).toEqual([
      "sala-juridica",
      "raio-x-processo",
    ]);
  });

  it("mantém o RBAC canônico: estagiário não ganha criação de caso", () => {
    expect(canRoleAccessPath("estagiario", "/entrada")).toBe(false);
    expect(canRoleAccessPath("estagiario", "/sala-juridica")).toBe(true);
    expect(canRoleAccessPath("estagiario", "/raio-x")).toBe(true);
  });

  it("continua respeitando override administrativo da Sala Jurídica", () => {
    const salaDesabilitada = override("sala-juridica", false);

    expect(
      lifecycleForPath("/sala-juridica", {
        "sala-juridica": salaDesabilitada,
      }),
    ).toBe(salaDesabilitada);
  });

  it("aplica lifecycle a subrotas wildcard do DPT360", () => {
    const dptSubroutes = override("dpt360-subroutes", false);

    expect(
      lifecycleForPath("/dpt360/radar", {
        "dpt360-subroutes": dptSubroutes,
      }),
    ).toBe(dptSubroutes);
  });

  it("prefere a rota dinâmica mais específica ao wildcard", () => {
    const companyDetail = override("dpt360-company-detail", false);
    const dptSubroutes = override("dpt360-subroutes", true);

    expect(
      lifecycleForPath("/dpt360/empresas/cliente-123", {
        "dpt360-company-detail": companyDetail,
        "dpt360-subroutes": dptSubroutes,
      }),
    ).toBe(companyDetail);
  });
});
