import { describe, expect, it } from "vitest";
import { hubDoRamo, podeCriarCasoNoHub } from "./RamosHub";

describe("hubDoRamo", () => {
  it("não gera rota para workspaces especializados desativados", () => {
    expect(hubDoRamo("empresarial")).toBeNull();
    expect(hubDoRamo("civil")).toBeNull();
    expect(hubDoRamo("criminal")).toBeNull();
  });

  it("não preserva links para especialidades antigas", () => {
    expect(hubDoRamo("societario")).toBeNull();
    expect(hubDoRamo("sucessoes")).toBeNull();
    expect(hubDoRamo("licitacoes")).toBeNull();
  });

  it("rejeita qualquer slug após a retirada do hub", () => {
    expect(hubDoRamo("internacional")).toBeNull();
    expect(hubDoRamo("area-inexistente")).toBeNull();
  });
});

describe("RBAC do Novo caso no hub", () => {
  it("espelha a lista de papéis da rota /casos/novo", () => {
    expect(podeCriarCasoNoHub("superadmin")).toBe(true);
    expect(podeCriarCasoNoHub("admin")).toBe(true);
    expect(podeCriarCasoNoHub("socio")).toBe(true);
    expect(podeCriarCasoNoHub("advogado")).toBe(true);
    expect(podeCriarCasoNoHub("secretaria")).toBe(true);
    expect(podeCriarCasoNoHub("advogado_auxiliar")).toBe(false);
    expect(podeCriarCasoNoHub("estagiario")).toBe(false);
    expect(podeCriarCasoNoHub("financeiro")).toBe(false);
  });
});
