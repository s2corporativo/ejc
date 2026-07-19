import { describe, expect, it } from "vitest";
import {
  LEGACY_REDIRECTS,
  STAFF_ROUTES,
  canRoleAccessPath,
  getNavigationModules,
} from "./moduleRegistry";

describe("moduleRegistry", () => {
  it("não possui chaves ou rotas duplicadas", () => {
    const keys = STAFF_ROUTES.map((route) => route.key);
    const paths = STAFF_ROUTES.map((route) => route.path);
    expect(new Set(keys).size).toBe(keys.length);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it("expõe o módulo jurídico como Áreas de Atuação", () => {
    const areas = STAFF_ROUTES.find((route) => route.key === "ramos");
    expect(areas?.label).toBe("Áreas de Atuação");
    expect(areas?.path).toBe("/areas-de-atuacao");
  });

  it("não possui aliases duplicados nem aliases sobre rotas canônicas", () => {
    const aliases = LEGACY_REDIRECTS.map((redirect) => redirect.from);
    const canonical = new Set(STAFF_ROUTES.map((route) => route.path));
    expect(new Set(aliases).size).toBe(aliases.length);
    for (const alias of aliases) expect(canonical.has(alias)).toBe(false);
  });

  it("oculta módulos internos, legados e não autorizados do menu", () => {
    const advogado = getNavigationModules("advogado");
    expect(advogado.some((module) => module.path === "/usuarios")).toBe(false);
    expect(advogado.some((module) => module.path === "/whatsapp")).toBe(false);
    expect(
      advogado.some((module) => module.path.includes("sala-de-guerra")),
    ).toBe(false);
  });

  it("mantém financeiro restrito aos perfis autorizados", () => {
    expect(canRoleAccessPath("financeiro", "/financeiro")).toBe(true);
    expect(canRoleAccessPath("advogado", "/financeiro")).toBe(false);
    expect(canRoleAccessPath("estagiario", "/financeiro")).toBe(false);
  });

  it("mantém preferências pessoais acessíveis a qualquer usuário interno", () => {
    expect(canRoleAccessPath("advogado", "/configuracoes")).toBe(true);
    expect(canRoleAccessPath("admin", "/configuracoes")).toBe(true);
  });

  it("preserva redirecionamentos das duplicidades consolidadas", () => {
    const map = new Map(
      LEGACY_REDIRECTS.map((redirect) => [redirect.from, redirect.to]),
    );
    expect(map.get("/partner-withdrawals")).toBe(
      "/financeiro?tab=societaria&sub=saques",
    );
    expect(map.get("/office-contracts")).toContain("contratos");
    expect(map.get("/agenda")).toBe("/atividades?view=calendario");
    expect(map.get("/kanban")).toBe("/atividades?view=kanban");
    expect(map.get("/assistente-ia")).toContain("/inteligencia");
    expect(map.get("/victory-vault")).toBe("/inteligencia?tab=conhecimento");
    expect(map.get("/knowledge-hub")).toBe("/inteligencia?tab=conhecimento");
    expect(map.get("/prazos")).toBe("/atividades?tipo=prazo");
    expect(map.get("/tarefas")).toBe("/atividades?tipo=tarefa");
    expect(map.get("/intimacoes")).toBe("/atividades?tipo=intimacao");
    expect(map.get("/suspensoes")).toBe("/atividades?tipo=suspensao");
    expect(map.get("/ramos")).toBe("/areas-de-atuacao");
    expect(map.get("/central-relacionamento")).toBe(
      "/atividades?tab=relacionamento",
    );
    expect(map.get("/dashboard")).toBe("/");
  });

  it("mantém o menu enxuto e o modo essencial com 7 destinos", () => {
    for (const role of ["superadmin", "admin", "socio", "advogado"]) {
      expect(getNavigationModules(role).length).toBeLessThanOrEqual(17);
      expect(
        getNavigationModules(role).some((m) => m.path === "/ferramentas"),
      ).toBe(true);
    }
    const navegacaoAdvogado = getNavigationModules("advogado");
    const advogado = navegacaoAdvogado.map((m) => m.path);
    const essenciais = navegacaoAdvogado
      .filter((m) => m.essential)
      .map((m) => m.path);
    expect(essenciais).toEqual([
      "/",
      "/casos",
      "/atividades",
      "/clientes",
      "/documentos",
      "/pecas",
      "/inteligencia",
    ]);
    expect(advogado).not.toContain("/casos/novo");
    expect(STAFF_ROUTES.some((m) => m.path === "/casos/novo")).toBe(true);

    // As implementações consolidadas continuam disponíveis para rollback e QA,
    // mas apenas em caminhos internos; as URLs públicas são aliases canônicos.
    const canonical = new Set(STAFF_ROUTES.map((route) => route.path));
    for (const path of [
      "/legado/prazos",
      "/legado/intimacoes",
      "/legado/tarefas",
      "/legado/suspensoes",
      "/legado/knowledge-hub",
      "/crm-leads",
      "/assinaturas",
      "/workflow",
      "/checklists",
      "/datajud",
      "/diario-oficial",
      "/radar-regulatorio",
      "/compliance/radar",
      "/noticias",
      "/produtividade",
      "/ia-governanca",
      "/auditoria",
      "/mapa-modulos",
      "/lixeira",
    ]) {
      expect(canonical.has(path)).toBe(true);
      expect(advogado).not.toContain(path);
    }
  });
});
