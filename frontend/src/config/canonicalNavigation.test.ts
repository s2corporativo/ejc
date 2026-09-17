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
  it("mantém exatamente os oito domínios na ordem canônica", () => {
    expect(CANONICAL_MAIN_NAV.map((item) => item.key)).toEqual([
      "dashboard",
      "casos",
      "clientes",
      "atividades",
      "documentos",
      "ramos",
      "financeiro",
      "configuracoes",
    ]);
  });

  it("preserva RBAC/lifecycle do conjunto recebido e aplica rótulos de menu", () => {
    const entrada = [
      mod("financeiro", "Financeiro"),
      mod("dashboard", "Início"),
      mod("atividades", "Prazos e Agenda"),
      mod("configuracoes", "Configurações"),
      mod("inteligencia", "IA Jurídica"),
    ];

    const saida = selectCanonicalMainNavigation(entrada);
    expect(saida.map((item) => [item.key, item.label])).toEqual([
      ["dashboard", "Início"],
      ["atividades", "Agenda"],
      ["financeiro", "Financeiro"],
      ["configuracoes", "Administrativo"],
    ]);
    expect(saida.some((item) => item.key === "inteligencia")).toBe(false);
  });
});
