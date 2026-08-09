import { describe, expect, it } from "vitest";
import { canRoleAccessPath } from "../config/moduleRegistry";
import {
  filterModulesByLifecycle,
  lifecycleForPath,
} from "./moduleLifecycle";
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

  it("mantém o RBAC canônico: estagiário não ganha criação de caso", () => {
    expect(canRoleAccessPath("estagiario", "/entrada")).toBe(false);
    expect(canRoleAccessPath("estagiario", "/sala-juridica")).toBe(true);
    expect(canRoleAccessPath("estagiario", "/raio-x")).toBe(true);
  });

  it("continua respeitando override administrativo da Sala Jurídica", () => {
    const override = {
      module_key: "sala-juridica",
      enabled: false,
      menu_visible: false,
      status: "disabled",
      reason: "Desabilitado para manutenção",
    } as ModuleLifecycleOverride;

    expect(lifecycleForPath("/sala-juridica", { "sala-juridica": override })).toBe(
      override,
    );
  });
});
