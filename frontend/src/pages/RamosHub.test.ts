import { describe, expect, it } from "vitest";
import { hubDoRamo, podeCriarCasoNoHub } from "./RamosHub";

describe("hubDoRamo", () => {
  it("gera rota contextual para workspaces especializados e aliases técnicos", () => {
    expect(hubDoRamo("empresarial")).toBe("/areas-de-atuacao/empresarial");
    expect(hubDoRamo("civil")).toBe("/areas-de-atuacao/civel");
    expect(hubDoRamo("criminal")).toBe("/areas-de-atuacao/penal");
  });

  it("preserva especialidades canônicas em workspaces próprios, sem achatamento", () => {
    expect(hubDoRamo("societario")).toBe("/areas-de-atuacao/societario");
    expect(hubDoRamo("sucessoes")).toBe("/areas-de-atuacao/sucessoes");
    expect(hubDoRamo("licitacoes")).toBe("/areas-de-atuacao/licitacoes");
    expect(hubDoRamo("societario")).not.toBe("/areas-de-atuacao/empresarial");
    expect(hubDoRamo("sucessoes")).not.toBe("/areas-de-atuacao/familia");
    expect(hubDoRamo("licitacoes")).not.toBe(
      "/areas-de-atuacao/administrativo",
    );
  });

  it("oferece workspace geral para área canônica e rejeita slug inexistente", () => {
    expect(hubDoRamo("internacional")).toBe("/areas-de-atuacao/internacional");
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
