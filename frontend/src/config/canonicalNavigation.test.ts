import { afterEach, describe, expect, it } from "vitest";
import {
  CANONICAL_MAIN_NAV,
  CANONICAL_MENU_9_NAV,
  isMenu9Enabled,
  selectCanonicalMainNavigation,
  selectMainNavigation,
  setMenu9Enabled,
} from "./canonicalNavigation";
import type { ModuleRoute } from "./moduleRegistry";

function mod(key: string, label = key): ModuleRoute {
  return {
    key,
    path: `/${key}`,
    label,
    description: key,
    group: "teste",
    icon: (() => null) as unknown as ModuleRoute["icon"],
    component: (() => null) as unknown as ModuleRoute["component"],
  };
}

describe("canonicalNavigation", () => {
  it("mantém exatamente os onze domínios da referência premium DPT, na ordem canônica", () => {
    expect(CANONICAL_MAIN_NAV.map((item) => item.key)).toEqual([
      "dashboard",
      "atividades",
      "clientes",
      "casos",
      "financeiro",
      "documentos",
      "inteligencia",
      "banco-teses",
      "radar",
      "produtividade",
      "configuracoes",
    ]);
  });

  it("aplica os rótulos da referência (Agenda e Prazos, Radar Operacional, Relatórios…)", () => {
    const entrada = [
      mod("financeiro", "Financeiro"),
      mod("dashboard", "Início"),
      mod("atividades", "Prazos e Agenda"),
      mod("configuracoes", "Configurações"),
      mod("inteligencia", "IA Jurídica"),
      mod("banco-teses", "Banco de Teses"),
      mod("radar", "Radar"),
      mod("produtividade", "Produtividade"),
    ];

    const saida = selectCanonicalMainNavigation(entrada);
    expect(saida.map((item) => [item.key, item.label])).toEqual([
      ["dashboard", "Início"],
      ["atividades", "Agenda e Prazos"],
      ["financeiro", "Financeiro"],
      ["inteligencia", "Inteligência Jurídica"],
      ["banco-teses", "Banco de Teses"],
      ["radar", "Radar Operacional"],
      ["produtividade", "Relatórios"],
      ["configuracoes", "Configurações"],
    ]);
  });

  it("preserva RBAC/lifecycle: módulo ausente da carteira não vira link morto", () => {
    const entrada = [
      mod("dashboard", "Início"),
      mod("clientes", "Clientes"),
      mod("inteligencia", "IA Jurídica"),
    ];

    const saida = selectCanonicalMainNavigation(entrada);
    expect(saida.map((item) => item.key)).toEqual([
      "dashboard",
      "clientes",
      "inteligencia",
    ]);
    expect(saida.some((item) => item.key === "casos")).toBe(false);
  });
});

describe("canonicalNavigation — Onda 1 (menu 9 do mapa funcional auditado)", () => {
  afterEach(() => {
    try {
      window.localStorage.removeItem("ejc_menu9");
    } catch {
      // jsdom sempre tem storage — guard apenas por segurança
    }
  });

  it("contrato canônico: exatamente os 9 domínios do mapa-alvo (§3), na ordem auditada", () => {
    expect(CANONICAL_MENU_9_NAV.map((item) => item.key)).toEqual([
      "dashboard",
      "clientes",
      "casos",
      "atividades",
      "pecas",
      "inteligencia",
      "financeiro",
      "portal",
      "configuracoes",
    ]);
  });

  it("aplica os rótulos alvo (Conhecimento Jurídico, Administração, Peças) e deixa fora os domínios absorvidos", () => {
    const entrada = [
      mod("dashboard", "Início"),
      mod("clientes", "Clientes"),
      mod("casos", "Casos"),
      mod("atividades", "Prazos e Agenda"),
      mod("pecas", "Peças"),
      mod("inteligencia", "Inteligência Jurídica"),
      mod("financeiro", "Financeiro"),
      mod("configuracoes", "Configurações"),
      // Domínios absorvidos pelo mapa 9 — rotas seguem vivas no registry,
      // mas NÃO aparecem no menu alvo:
      mod("documentos", "Documentos"),
      mod("banco-teses", "Banco de Teses"),
      mod("radar", "Radar"),
      mod("produtividade", "Produtividade"),
    ];

    const saida = selectMainNavigation(entrada, { menu9: true });
    expect(saida.map((item) => [item.key, item.label])).toEqual([
      ["dashboard", "Início"],
      ["clientes", "Clientes"],
      ["casos", "Casos"],
      ["atividades", "Agenda e Prazos"],
      ["pecas", "Peças"],
      ["inteligencia", "Conhecimento Jurídico"],
      ["financeiro", "Financeiro"],
      ["configuracoes", "Administração"],
    ]);
    expect(
      saida.some((item) =>
        ["documentos", "banco-teses", "radar", "produtividade"].includes(
          item.key,
        ),
      ),
    ).toBe(false);
  });

  it("portal sem ModuleRoute de staff não vira link morto (descartado em runtime)", () => {
    const saida = selectMainNavigation([mod("dashboard", "Início")], {
      menu9: true,
    });
    expect(saida.map((item) => item.key)).toEqual(["dashboard"]);
    expect(saida.some((item) => item.key === "portal")).toBe(false);
  });

  it("flag OFF (default) mantém os 11 domínios da referência DPT — rollback imediato", () => {
    const entrada = [
      mod("dashboard", "Início"),
      mod("documentos", "Documentos"),
      mod("banco-teses", "Banco de Teses"),
      mod("radar", "Radar"),
      mod("produtividade", "Produtividade"),
      mod("configuracoes", "Configurações"),
    ];

    const saida = selectMainNavigation(entrada, { menu9: false });
    expect(saida.map((item) => item.key)).toEqual([
      "dashboard",
      "documentos",
      "banco-teses",
      "radar",
      "produtividade",
      "configuracoes",
    ]);
  });

  it("sem override explícito, o seletor honra a flag (localStorage > env)", () => {
    // Sem flag: env default undefined → menu 11.
    const entrada = [
      mod("dashboard", "Início"),
      mod("inteligencia", "Inteligência Jurídica"),
      mod("configuracoes", "Configurações"),
    ];
    expect(isMenu9Enabled()).toBe(false);
    expect(selectMainNavigation(entrada).map((item) => item.key)).toEqual([
      "dashboard",
      "inteligencia",
      "configuracoes",
    ]);

    // Override local ON → menu 9 (inteligencia relabelada, configurações vira
    // Administração).
    setMenu9Enabled(true);
    expect(isMenu9Enabled()).toBe(true);
    const saida9 = selectMainNavigation(entrada);
    expect(saida9.map((item) => item.label)).toEqual([
      "Início",
      "Conhecimento Jurídico",
      "Administração",
    ]);

    // Override local OFF vence qualquer env.
    setMenu9Enabled(false);
    expect(isMenu9Enabled()).toBe(false);
  });
});
