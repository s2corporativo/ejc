import { describe, expect, it } from "vitest";
import {
  GRUPOS_AREAS,
  areaCombinaBusca,
  casosGeraisPath,
  configWorkspaceDaArea,
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

  it("mantém especialidades no próprio slug e só aplica aliases técnicos", () => {
    expect(hubSlugDaArea("societario")).toBe("societario");
    expect(hubSlugDaArea("sucessoes")).toBe("sucessoes");
    expect(hubSlugDaArea("licitacoes")).toBe("licitacoes");
    expect(hubSlugDaArea("societario")).not.toBe("empresarial");
    expect(hubSlugDaArea("sucessoes")).not.toBe("familia");
    expect(hubSlugDaArea("licitacoes")).not.toBe("administrativo");
    expect(hubSlugDaArea("civil")).toBe("civel");
    expect(hubSlugDaArea("criminal")).toBe("penal");
    expect(hubSlugDaArea("area-inexistente")).toBeNull();
  });

  it("reutiliza a mesma configuração nas áreas fallback", () => {
    const primeira = configWorkspaceDaArea("societario");
    const segunda = configWorkspaceDaArea("societario");
    expect(primeira).toBeDefined();
    expect(segunda).toBe(primeira);
  });

  it("rejeita propriedades herdadas do Object.prototype como slugs", () => {
    for (const slug of ["constructor", "toString", "valueOf"]) {
      expect(hubSlugDaArea(slug)).toBeNull();
      expect(configWorkspaceDaArea(slug)).toBeUndefined();
    }
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
