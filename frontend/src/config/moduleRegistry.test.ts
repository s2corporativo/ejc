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
    expect(areas?.path).toBe("/ramos");
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
    expect(map.get("/victory-vault")).toBe("/knowledge-hub");
    expect(map.get("/central-relacionamento")).toBe(
      "/atividades?tab=relacionamento",
    );
    expect(map.get("/dashboard")).toBe("/");
  });

  it("mantém o menu enxuto (~15 destinos visíveis por perfil)", () => {
    for (const role of ["superadmin", "admin", "socio", "advogado"]) {
      expect(getNavigationModules(role).length).toBeLessThanOrEqual(17);
      // /ferramentas não tem restrição de papel: visível para toda a equipe.
      expect(
        getNavigationModules(role).some((m) => m.path === "/ferramentas"),
      ).toBe(true);
    }
    // Telas-fim essenciais continuam visíveis para o advogado.
    const advogado = getNavigationModules("advogado").map((m) => m.path);
    for (const path of ["/", "/casos/novo", "/casos", "/atividades", "/prazos", "/clientes"]) {
      expect(advogado).toContain(path);
    }
    // Rotas podadas permanecem ativas (sem 404), apenas fora do menu.
    const canonical = new Set(STAFF_ROUTES.map((route) => route.path));
    for (const path of [
      "/tarefas",
      "/suspensoes",
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
