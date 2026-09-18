import { describe, expect, it } from "vitest";
import {
  CANONICAL_MAIN_NAV,
  selectCanonicalMainNavigation,
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
