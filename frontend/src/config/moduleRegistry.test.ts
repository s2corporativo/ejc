import { describe, expect, it } from "vitest";
import { filterModulesByLifecycle } from "../lib/moduleLifecycle";
import {
  LEGACY_REDIRECTS,
  MODULE_GROUP_ORDER,
  STAFF_ROUTES,
  canRoleAccessPath,
  getNavigationModules,
  groupNavigationModules,
  routePatternMatches,
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

  it("declara backendPrefixes só com o prefixo canônico /api (nunca /api/v1)", () => {
    // /api/v1 é alias de compatibilidade reescrito por middleware; o metadado
    // descreve endereços canônicos — resíduo já induziu auditoria a erro.
    for (const route of STAFF_ROUTES) {
      for (const prefix of route.backendPrefixes ?? []) {
        expect(prefix, `${route.key}: ${prefix}`).toMatch(/^\/api\//);
        expect(prefix, `${route.key}: ${prefix}`).not.toMatch(/^\/api\/v1\//);
      }
    }
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
      expect(
        canRoleAccessPath(role, "/dpt360/empresas/cliente-123"),
        role,
      ).toBe(true);
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
      expect(
        canRoleAccessPath(role, "/dpt360/empresas/cliente-123"),
        role,
      ).toBe(false);
    }
  });

  it("faz matching de parâmetros dinâmicos sem aceitar profundidade indevida", () => {
    expect(routePatternMatches("/clientes/:clientId", "/clientes/abc")).toBe(
      true,
    );
    expect(routePatternMatches("/clientes/:clientId", "/clientes/abc/x")).toBe(
      false,
    );
    expect(routePatternMatches("/casos/:id/jornada", "/casos/42/jornada")).toBe(
      true,
    );
    expect(routePatternMatches("/dpt360/*", "/dpt360/empresas/abc")).toBe(true);
  });

  it("espelha RBAC do dossiê dinâmico de cliente", () => {
    for (const role of [
      "superadmin",
      "admin",
      "socio",
      "advogado",
      "secretaria",
    ]) {
      expect(canRoleAccessPath(role, "/clientes/cliente-123"), role).toBe(true);
    }
    for (const role of ["financeiro", "estagiario", "advogado_auxiliar"]) {
      expect(canRoleAccessPath(role, "/clientes/cliente-123"), role).toBe(
        false,
      );
    }
  });

  it("mantém Entrada Jurídica como porta visível sem prometer IA à secretaria", () => {
    const entrada = STAFF_ROUTES.find((route) => route.key === "entrada");
    expect(entrada?.label).toBe("Entrada Jurídica");
    expect(entrada?.essential).toBe(true);
    expect(canRoleAccessPath("advogado", "/entrada")).toBe(true);
    expect(canRoleAccessPath("secretaria", "/entrada")).toBe(true);
    expect(canRoleAccessPath("financeiro", "/entrada")).toBe(false);
    expect(
      STAFF_ROUTES.find((route) => route.key === "caso-novo")?.showInNav,
    ).toBe(false);
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

    expect(advogado.find((item) => item.path === "/entrada")?.essential).toBe(
      true,
    );
    expect(advogado.some((item) => item.path === "/sala-juridica")).toBe(false);
    expect(advogado.some((item) => item.path === "/financeiro")).toBe(false);
    expect(socio.find((item) => item.path === "/financeiro")?.essential).toBe(
      true,
    );
  });

  it("mantém o Raio-X canônico e o consolida no menu apenas quando há Entrada", () => {
    const advogado = getProductionNavigation("advogado");
    const auxiliar = getProductionNavigation("advogado_auxiliar");
    const raioX = STAFF_ROUTES.find((item) => item.path === "/raio-x");

    expect(canRoleAccessPath("advogado", "/raio-x")).toBe(true);
    expect(raioX?.showInNav).toBe(true);
    expect(raioX?.essential).toBe(false);
    expect(advogado.some((item) => item.path === "/raio-x")).toBe(false);
    expect(auxiliar.some((item) => item.path === "/raio-x")).toBe(true);
    expect(auxiliar.some((item) => item.path === "/sala-juridica")).toBe(true);
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
    // PR #1378: Sociedade saiu de dentro do Financeiro e virou módulo próprio
    // (`/gestao-escritorio/sociedade`, RBAC de gestão). O redirect legado
    // acompanha o novo destino — retirada de sócio não é caixa operacional.
    expect(map.get("/partner-withdrawals")).toBe(
      "/gestao-escritorio/sociedade?sub=saques",
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
    // Consolidação 2026-08: as telas /legado/* foram aposentadas e viraram
    // redirects diretos para o destino final (nunca redirect → redirect).
    expect(map.get("/legado/prazos")).toBe("/atividades?tipo=prazo");
    expect(map.get("/legado/tarefas")).toBe("/atividades?tipo=tarefa");
    expect(map.get("/legado/intimacoes")).toBe("/atividades?tipo=intimacao");
    expect(map.get("/legado/suspensoes")).toBe("/atividades?tipo=suspensao");
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
      "/entrada",
      "/casos",
      "/atividades",
      "/clientes",
      "/documentos",
      "/pecas",
      "/dpt360",
      "/inteligencia",
    ]);
    expect(advogado).not.toContain("/casos/novo");
    expect(STAFF_ROUTES.some((m) => m.path === "/casos/novo")).toBe(true);

    const canonical = new Set(STAFF_ROUTES.map((route) => route.path));
    for (const path of [
      "/crm-leads",
      "/assinaturas",
      "/workflow",
      "/checklists",
      "/datajud",
      "/diario-oficial",
      "/radar",
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
    expect(canRoleAccessPath("cliente_externo", "/radar")).toBe(false);
  });
});

describe("navegação canônica do shell (Fase 4)", () => {
  it("não tem rótulo de módulo sobrescrito fora do registry — fonte única", () => {
    // O shell (LayoutReference) passou a consumir item.label direto do
    // registry. Se um rótulo canônico regredir aqui, sidebar e CommandPalette
    // divergem de novo (auditoria §2.6 #2).
    const labels = new Map(
      STAFF_ROUTES.map((route) => [route.key, route.label]),
    );
    expect(labels.get("atividades")).toBe("Prazos e Agenda");
    expect(labels.get("inteligencia")).toBe("IA Jurídica");
    expect(labels.get("configuracoes")).toBe("Configurações");
    expect(labels.get("financeiro")).toBe("Financeiro");
  });

  it("deriva a lista primária exatamente da flag essential por papel", () => {
    // Espelha a regra do LayoutReference: primary = visible.filter(essential).
    for (const [role, esperado] of [
      [
        "advogado",
        [
          "/",
          "/entrada",
          "/casos",
          "/atividades",
          "/clientes",
          "/documentos",
          "/pecas",
          "/dpt360",
          "/inteligencia",
        ],
      ],
      [
        "socio",
        [
          "/",
          "/entrada",
          "/casos",
          "/atividades",
          "/clientes",
          "/documentos",
          "/pecas",
          "/dpt360",
          "/inteligencia",
          "/financeiro",
        ],
      ],
    ] as const) {
      const primaria = getProductionNavigation(role).filter(
        (m) => m.essential,
      );
      expect(primaria.map((m) => m.path), role).toEqual(esperado);
    }
  });

  it("groupNavigationModules produz blocos consecutivos na ordem dos grupos", () => {
    const navegacao = getProductionNavigation("socio");
    const grupos = groupNavigationModules(navegacao);

    // sem perda nem duplicação
    expect(grupos.flatMap((g) => g.items)).toEqual(navegacao);

    // blocos consecutivos: nenhum grupo reaparece depois de encerrado
    const nomes = grupos.map((g) => g.name);
    expect(new Set(nomes).size).toBe(nomes.length);

    // a ordem dos blocos respeita MODULE_GROUP_ORDER
    const posicao = new Map(MODULE_GROUP_ORDER.map((g, i) => [g, i]));
    const indices = nomes.map((n) => posicao.get(n) ?? Number.MAX_SAFE_INTEGER);
    expect(indices).toEqual([...indices].sort((a, b) => a - b));

    // caso determinístico com módulos reais do registry
    const pega = (key: string) => {
      const found = STAFF_ROUTES.find((route) => route.key === key);
      expect(found, key).toBeTruthy();
      return found!;
    };
    const mistura = [
      pega("dashboard"),
      pega("casos"),
      pega("dpt360"),
      pega("inteligencia"),
    ];
    const blocos = groupNavigationModules(mistura);
    expect(blocos.map((g) => g.name)).toEqual([
      "Trabalhar um caso",
      "Pesquisar & IA",
    ]);
    expect(blocos[0].items.map((i) => i.key)).toEqual(["dashboard", "casos"]);
    expect(blocos[1].items.map((i) => i.key)).toEqual([
      "dpt360",
      "inteligencia",
    ]);
  });
});
