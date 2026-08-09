import { describe, expect, it } from "vitest";
import { RAMOS } from "./ramosConfig";
import {
  AREAS_PRINCIPAIS_PADRAO,
  GRUPOS_AREAS,
  abasDoWorkspace,
  buscarFerramentas,
  casosDaAreaPath,
  ferramentasDoWorkspace,
  hubSlugDaArea,
  importacaoDaAreaPath,
  novoCasoPath,
  subtituloDoWorkspace,
  tituloDoWorkspace,
} from "./areasWorkspace";

describe("areasWorkspace", () => {
  it("mantém poucos acessos principais e organiza a taxonomia em núcleos", () => {
    expect(AREAS_PRINCIPAIS_PADRAO).toHaveLength(8);
    expect(GRUPOS_AREAS.map((grupo) => grupo.id)).toEqual([
      "pessoas",
      "negocios",
      "publico",
      "especialidades",
    ]);
  });

  it("subordina sucessões, societário e licitações apenas na navegação", () => {
    expect(hubSlugDaArea("sucessoes")).toBe("familia");
    expect(hubSlugDaArea("societario")).toBe("empresarial");
    expect(hubSlugDaArea("licitacoes")).toBe("administrativo");
  });

  it("apresenta Cível Geral sem repetir ferramentas de consumidor, família e imobiliário", () => {
    const civel = RAMOS.civel;
    const grupos = ferramentasDoWorkspace(civel).map((ferramenta) => ferramenta.grupo);
    expect(tituloDoWorkspace(civel)).toBe("Direito Cível Geral");
    expect(subtituloDoWorkspace(civel)).toContain("Responsabilidade civil");
    expect(grupos).not.toContain("Consumidor");
    expect(grupos).not.toContain("Família");
    expect(grupos).not.toContain("Imobiliário");
    expect(ferramentasDoWorkspace(civel).some((ferramenta) => ferramenta.id === "custas-tjmg")).toBe(true);
    expect(ferramentasDoWorkspace(civel).some((ferramenta) => ferramenta.id === "prazos-contestacao")).toBe(true);
  });

  it("mantém busca central por ferramentas sem recolocar as duplicidades de Cível", () => {
    const anpp = buscarFerramentas("ANPP");
    expect(anpp.some((resultado) => resultado.areaSlug === "penal" && resultado.ferramenta.id === "anpp")).toBe(true);

    const alimentos = buscarFerramentas("alimentos");
    expect(alimentos.some((resultado) => resultado.areaSlug === "civel" && resultado.ferramenta.grupo === "Família")).toBe(false);
  });

  it("define abas conforme os recursos reais de cada workspace", () => {
    expect(abasDoWorkspace(RAMOS.bancario)).toEqual(
      expect.arrayContaining(["visao-geral", "casos", "ferramentas", "analise", "referencias"]),
    );
    expect(abasDoWorkspace(RAMOS.civel)).toContain("ferramentas");
    expect(abasDoWorkspace(RAMOS.civel)).not.toContain("analise");
  });

  it("gera entradas canônicas de caso com a área pré-selecionada", () => {
    expect(novoCasoPath("ambiental")).toBe("/casos/novo?area=ambiental");
    expect(casosDaAreaPath("ambiental")).toBe("/casos?area=ambiental");
    expect(importacaoDaAreaPath("ambiental")).toBe(
      "/casos/novo?modo=documento&area=ambiental",
    );
  });
});
