import { describe, expect, it } from "vitest";
import { MODULE_SEARCH_ALIASES, textoBuscaModulo } from "./CommandPalette";

describe("CommandPalette — aliases de navegação removida", () => {
  const modulo = (key: string, label: string, description = "") => ({
    key,
    label,
    description,
  });

  it("preserva todos os rótulos históricos retirados da lateral", () => {
    const esperados = {
      atividades: "Agenda e Prazos",
      inteligencia: "Inteligência Jurídica",
      radar: "Radar Operacional",
      produtividade: "Relatórios",
    };

    for (const [key, alias] of Object.entries(esperados)) {
      expect(MODULE_SEARCH_ALIASES[key]).toContain(alias);
    }
  });

  it("indexa Radar Operacional e Relatórios mesmo com labels curtos no registry", () => {
    expect(textoBuscaModulo(modulo("radar", "Radar"))).toContain(
      "radar operacional",
    );
    expect(textoBuscaModulo(modulo("produtividade", "Produtividade"))).toContain(
      "relatórios",
    );
  });
});
