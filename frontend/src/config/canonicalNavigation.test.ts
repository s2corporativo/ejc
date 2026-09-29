import { afterEach, describe, expect, it } from "vitest";
import {
  CANONICAL_MAIN_NAV,
  CANONICAL_CORE_NAV,
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

describe("canonicalNavigation — menu Core mínimo", () => {
  afterEach(() => {
    try {
      window.localStorage.removeItem("ejc_menu9");
    } catch {
      // jsdom sempre tem storage — guard apenas por segurança
    }
  });

  it("expõe somente os cinco destinos estruturais do escritório", () => {
    expect(CANONICAL_CORE_NAV.map((item) => item.key)).toEqual([
      "dashboard",
      "clientes",
      "casos",
      "financeiro",
      "configuracoes",
    ]);
    expect(CANONICAL_MENU_9_NAV).toBe(CANONICAL_CORE_NAV);
  });

  it("rotula Casos como Casos e Processos e mantém áreas operacionais fora da lateral", () => {
    const entrada = [
      mod("dashboard", "Início"),
      mod("clientes", "Clientes"),
      mod("casos", "Casos"),
      mod("financeiro", "Financeiro"),
      mod("configuracoes", "Configurações"),
      mod("atividades", "Prazos e Agenda"),
      mod("pecas", "Peças"),
      mod("inteligencia", "Inteligência Jurídica"),
      mod("documentos", "Documentos"),
      mod("banco-teses", "Banco de Teses"),
      mod("radar", "Radar"),
      mod("produtividade", "Produtividade"),
    ];

    const saida = selectMainNavigation(entrada, { menu9: true });
    expect(saida.map((item) => [item.key, item.label])).toEqual([
      ["dashboard", "Início"],
      ["clientes", "Clientes"],
      ["casos", "Casos e Processos"],
      ["financeiro", "Financeiro"],
      ["configuracoes", "Administração"],
    ]);
    expect(
      saida.some((item) =>
        [
          "atividades",
          "pecas",
          "inteligencia",
          "documentos",
          "banco-teses",
          "radar",
          "produtividade",
        ].includes(item.key),
      ),
    ).toBe(false);
  });

  it("preserva RBAC/lifecycle: destino ausente da carteira não vira link morto", () => {
    const entrada = [
      mod("dashboard", "Início"),
      mod("clientes", "Clientes"),
      mod("casos", "Casos"),
      mod("configuracoes", "Configurações"),
    ];
    const saida = selectMainNavigation(entrada, { menu9: true });
    expect(saida.map((item) => item.key)).toEqual([
      "dashboard",
      "clientes",
      "casos",
      "configuracoes",
    ]);
    expect(saida.some((item) => item.key === "financeiro")).toBe(false);
  });

  it("flag OFF mantém os 11 domínios históricos como rollback", () => {
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

  it("default ATIVO usa o Core; override local OFF restaura menu amplo", () => {
    const entrada = [
      mod("dashboard", "Início"),
      mod("clientes", "Clientes"),
      mod("casos", "Casos"),
      mod("inteligencia", "Inteligência Jurídica"),
      mod("configuracoes", "Configurações"),
    ];

    expect(isMenu9Enabled()).toBe(true);
    expect(selectMainNavigation(entrada).map((item) => item.label)).toEqual([
      "Início",
      "Clientes",
      "Casos e Processos",
      "Administração",
    ]);

    setMenu9Enabled(false);
    expect(isMenu9Enabled()).toBe(false);
    expect(selectMainNavigation(entrada).map((item) => item.key)).toEqual([
      "dashboard",
      "clientes",
      "casos",
      "inteligencia",
      "configuracoes",
    ]);

    setMenu9Enabled(true);
    expect(isMenu9Enabled()).toBe(true);
    expect(selectMainNavigation(entrada).map((item) => item.label)).toEqual([
      "Início",
      "Clientes",
      "Casos e Processos",
      "Administração",
    ]);
  });
});
