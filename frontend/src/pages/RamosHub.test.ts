import { describe, expect, it } from "vitest";
import { hubDoRamo, podeCriarCasoNoHub } from "./RamosHub";

describe("hubDoRamo", () => {
  it("gera rota canônica somente para workspaces realmente existentes", () => {
    expect(hubDoRamo("empresarial")).toBe("/areas-de-atuacao/empresarial");
    expect(hubDoRamo("civil")).toBe("/areas-de-atuacao/civel");
    expect(hubDoRamo("criminal")).toBe("/areas-de-atuacao/penal");
  });

  it("não achata especialidades canônicas em outro workspace", () => {
    expect(hubDoRamo("societario")).toBeNull();
    expect(hubDoRamo("sucessoes")).toBeNull();
    expect(hubDoRamo("licitacoes")).toBeNull();
  });

  it("não cria rota para área inexistente ou sem workspace", () => {
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
