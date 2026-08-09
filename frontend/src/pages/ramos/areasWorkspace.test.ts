import { describe, expect, it } from "vitest";
import {
  GRUPOS_AREAS,
  areaCombinaBusca,
  casosGeraisPath,
  hubSlugDaArea,
  importacaoPath,
  novoCasoPath,
  normalizarBusca,
  type AreaResumo,
} from "./areasWorkspace";

const AREA: AreaResumo = {
  slug: "tributario",
  nome: "Direito Tributário",
  ordem: 70,
};

describe("Áreas de Atuação — contratos seguros", () => {
  it("mantém as 25 áreas canônicas em um único grupo cada", () => {
    const slugs = GRUPOS_AREAS.flatMap((grupo) => grupo.slugs);
    expect(slugs).toHaveLength(25);
    expect(new Set(slugs).size).toBe(25);
    expect(slugs).toContain("societario");
    expect(slugs).toContain("sucessoes");
    expect(slugs).toContain("licitacoes");
  });

  it("não reclassifica especialidades em núcleos pai", () => {
    expect(hubSlugDaArea("societario")).toBeNull();
    expect(hubSlugDaArea("sucessoes")).toBeNull();
    expect(hubSlugDaArea("licitacoes")).toBeNull();
    expect(hubSlugDaArea("civil")).toBe("civel");
    expect(hubSlugDaArea("criminal")).toBe("penal");
  });

  it("não codifica ?area em rotas que Casos.tsx ainda não consome", () => {
    expect(casosGeraisPath()).toBe("/casos");
    expect(novoCasoPath()).toBe("/casos/novo");
    expect(importacaoPath()).toBe("/casos/novo?modo=documento");
    expect(casosGeraisPath()).not.toContain("area=");
    expect(novoCasoPath()).not.toContain("area=");
  });

  it("normaliza acentos e busca também pelos recursos do workspace", () => {
    expect(normalizarBusca("Tributário")).toBe("tributario");
    expect(areaCombinaBusca(AREA, "tributario")).toBe(true);
    expect(areaCombinaBusca(AREA, "execução fiscal")).toBe(true);
    expect(areaCombinaBusca(AREA, "assunto inexistente xyz")).toBe(false);
  });
});
