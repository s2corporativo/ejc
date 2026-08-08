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

  it("destaca a Entrada Única e o Financeiro apenas para os perfis autorizados", () => {
    const advogado = getProductionNavigation("advogado");
    const socio = getProductionNavigation("socio");
    expect(
      advogado.find((item) => item.path === "/entrada")?.essential,
    ).toBe(true);
    expect(advogado.some((item) => item.path === "/financeiro")).toBe(false);
    expect(socio.find((item) => item.path === "/financeiro")?.essential).toBe(
      true,
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
      expect(getProductionNavigation(role).length).toBeLessThanOrEqual(17);
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
      "/entrada",
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

// ── F3: Sala Jurídica e Raio-X viraram modos da Entrada Única ────────────────
// Eram duas portas de menu concorrentes com a Entrada de Caso — nenhuma
// terminava sozinha no fluxo que a auditoria pedia. Viraram `?modo=sala` e
// `?modo=raio-x` de /entrada, mesmo padrão do Radar. Diferente do Radar: aqui
// o RBAC não pode usar "o mais restritivo vence" — Sala/Raio-X já admitiam
// estagiário e advogado_auxiliar, e a Entrada sozinha exigia compliance
// (advogado+). Usar o mais restrito TIRARIA uma ferramenta que esses papéis
// já tinham; a porta usa o mais AMPLO dos três porque o backend continua
// sendo quem barra os atos de advogado (criar caso, enviar mensagem,
// converter) — este teste também confirma que ninguém GANHOU rota nova.
describe("entrada única consolidada (F3)", () => {
  it("expõe uma única porta e aposenta as duas rotas antigas", () => {
    const rotas = new Set(STAFF_ROUTES.map((r) => r.path));
    expect(rotas.has("/entrada")).toBe(true);
    expect(rotas.has("/sala-juridica")).toBe(false);
    expect(rotas.has("/raio-x")).toBe(false);
  });

  it("redireciona os dois caminhos legados para o modo correspondente", () => {
    const destino = new Map(LEGACY_REDIRECTS.map((r) => [r.from, r.to]));
    expect(destino.get("/sala-juridica")).toBe("/entrada?modo=sala");
    expect(destino.get("/raio-x")).toBe("/entrada?modo=raio-x");
  });

  it("preserva o acesso de estagiário/advogado_auxiliar que a Sala e o Raio-X já davam", () => {
    for (const papel of [
      "superadmin",
      "admin",
      "socio",
      "advogado",
      "advogado_auxiliar",
      "estagiario",
    ]) {
      expect(canRoleAccessPath(papel, "/entrada"), papel).toBe(true);
    }
    for (const papel of ["financeiro", "secretaria"]) {
      expect(canRoleAccessPath(papel, "/entrada"), papel).toBe(false);
    }
    expect(canRoleAccessPath("cliente_externo", "/entrada")).toBe(false);
  });
});
