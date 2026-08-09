import { describe, expect, it } from "vitest";
import { filterModulesByLifecycle } from "../lib/moduleLifecycle";
import {
  LEGACY_REDIRECTS,
  STAFF_ROUTES,
  canRoleAccessPath,
  getNavigationModules,
} from "./moduleRegistry";

function getProductionNavigation(role: string) {
  return filterModulesByLifecycle(getNavigationModules(role), {});
}

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

  it("registra o DPT Empresarial 360 como workspace essencial sem alargar RBAC", () => {
    const dpt = STAFF_ROUTES.find((route) => route.key === "dpt360");
    expect(dpt?.path).toBe("/dpt360");
    expect(dpt?.showInNav).toBe(true);
    expect(dpt?.essential).toBe(true);
    expect(STAFF_ROUTES.some((route) => route.path === "/dpt360/*")).toBe(true);

    for (const role of ["superadmin", "admin", "socio", "advogado"]) {
      expect(canRoleAccessPath(role, "/dpt360"), role).toBe(true);
      expect(canRoleAccessPath(role, "/dpt360/empresas"), role).toBe(true);
    }
    for (const role of [
      "advogado_auxiliar",
      "estagiario",
      "financeiro",
      "secretaria",
      "cliente_externo",
    ]) {
      expect(canRoleAccessPath(role, "/dpt360"), role).toBe(false);
      expect(canRoleAccessPath(role, "/dpt360/empresas"), role).toBe(false);
    }
  });

  it("não possui aliases duplicados nem aliases sobre rotas canônicas", () => {
    const aliases = LEGACY_REDIRECTS.map((redirect) => redirect.from);
    const canonical = new Set(STAFF_ROUTES.map((route) => route.path));
    expect(new Set(aliases).size).toBe(aliases.length);
    for (const alias of aliases) expect(canonical.has(alias)).toBe(false);
  });

  it("oculta módulos internos, legados e não autorizados do menu efetivo", () => {
    const advogado = getProductionNavigation("advogado");
    expect(advogado.some((module) => module.path === "/usuarios")).toBe(false);
    expect(advogado.some((module) => module.path === "/whatsapp")).toBe(false);
    expect(advogado.some((module) => module.key === "knowledge-hub")).toBe(
      false,
    );
  });

  it("mantém financeiro restrito aos perfis autorizados", () => {
    expect(canRoleAccessPath("financeiro", "/financeiro")).toBe(true);
    expect(canRoleAccessPath("advogado", "/financeiro")).toBe(false);
    expect(canRoleAccessPath("estagiario", "/financeiro")).toBe(false);
  });

  it("nega financeiro em Peças — espelha o backend (Issue #694, allowlist EQUIPE_JURIDICA em POST /pecas/gerar)", () => {
    expect(canRoleAccessPath("financeiro", "/pecas")).toBe(false);
    expect(canRoleAccessPath("estagiario", "/pecas")).toBe(true);
    expect(canRoleAccessPath("advogado", "/pecas")).toBe(true);
    expect(
      getProductionNavigation("financeiro").some((m) => m.path === "/pecas"),
    ).toBe(false);
  });

  it("destaca a Entrada Jurídica e o Financeiro apenas para os perfis autorizados", () => {
    const advogado = getProductionNavigation("advogado");
    const socio = getProductionNavigation("socio");
    expect(advogado.find((item) => item.path === "/entrada")?.essential).toBe(
      true,
    );
    expect(advogado.some((item) => item.path === "/sala-juridica")).toBe(false);
    expect(advogado.some((item) => item.path === "/raio-x")).toBe(false);
    expect(advogado.some((item) => item.path === "/financeiro")).toBe(false);
    expect(socio.find((item) => item.path === "/financeiro")?.essential).toBe(
      true,
    );
  });

  it("preserva Sala/Raio-X como rotas técnicas, sem duplicá-las no menu do advogado", () => {
    const advogado = getProductionNavigation("advogado");
    const raioX = STAFF_ROUTES.find((item) => item.path === "/raio-x");
    const sala = STAFF_ROUTES.find((item) => item.path === "/sala-juridica");
    expect(canRoleAccessPath("advogado", "/raio-x")).toBe(true);
    expect(canRoleAccessPath("advogado", "/sala-juridica")).toBe(true);
    expect(raioX?.showInNav).toBe(true);
    expect(sala?.showInNav).toBe(true);
    expect(advogado.some((item) => item.path === "/raio-x")).toBe(false);
    expect(advogado.some((item) => item.path === "/sala-juridica")).toBe(false);
    expect(STAFF_ROUTES.some((item) => item.path === "/sala-analise")).toBe(
      false,
    );
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

  it("mantém o menu enxuto e o modo essencial por perfil", () => {
    for (const role of ["superadmin", "admin", "socio", "advogado"]) {
      expect(getProductionNavigation(role).length).toBeLessThanOrEqual(18);
      expect(
        getProductionNavigation(role).some((m) => m.path === "/ferramentas"),
      ).toBe(true);
    }
    const navegacaoAdvogado = getProductionNavigation("advogado");
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
      "/dpt360",
      "/entrada",
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
      "/crm-leads",
      "/assinaturas",
      "/workflow",
      "/checklists",
      "/datajud",
      "/diario-oficial",
      "/radar",
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

// ── Onda 2: os dois radares viraram uma porta ────────────────────────────────
// O feed de compliance já consolidava Diário Oficial + monitoramento
// regulatório + autos ambientais; o radar regulatório era o DIGEST da mesma
// matéria. Duas entradas de menu para a mesma pergunta é atrito — viraram
// `?modo=feed|digest` de /radar. Este teste trava a consolidação e, sobretudo,
// que a fusão NÃO alargou quem enxerga o feed de risco.
describe("radar consolidado", () => {
  it("expõe uma única porta e aposenta as duas rotas antigas", () => {
    const rotas = new Set(STAFF_ROUTES.map((r) => r.path));
    expect(rotas.has("/radar")).toBe(true);
    expect(rotas.has("/radar-regulatorio")).toBe(false);
    expect(rotas.has("/compliance/radar")).toBe(false);
  });

  it("redireciona os dois caminhos legados, o digest para o seu modo", () => {
    const destino = new Map(LEGACY_REDIRECTS.map((r) => [r.from, r.to]));
    expect(destino.get("/compliance/radar")).toBe("/radar");
    expect(destino.get("/radar-regulatorio")).toBe("/radar?modo=digest");
  });

  it("herda o RBAC mais restritivo dos dois — a fusão não alarga acesso", () => {
    // A versão anterior deste teste comparava /radar com /compliance/radar.
    // Como /compliance/radar deixou de ser rota, os dois lados davam `false` e
    // a asserção passava por VÁCUO — não validava matriz nenhuma. Agora a
    // matriz de ROLES.compliance é afirmada papel a papel.
    for (const papel of ["superadmin", "admin", "socio", "advogado"]) {
      expect(canRoleAccessPath(papel, "/radar"), papel).toBe(true);
    }
    for (const papel of [
      "advogado_auxiliar",
      "estagiario",
      "financeiro",
      "secretaria",
    ]) {
      expect(canRoleAccessPath(papel, "/radar"), papel).toBe(false);
    }
    // E o portal do cliente jamais alcança o feed de risco do escritório.
    expect(canRoleAccessPath("cliente_externo", "/radar")).toBe(false);
  });
});
