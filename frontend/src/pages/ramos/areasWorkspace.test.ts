import { describe, expect, it } from "vitest";
import {
  GRUPOS_AREAS,
  areaCombinaBusca,
  buscarFerramentas,
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

// Regressão: o catálogo apresentava duas calculadoras para a mesma regra penal.
describe("prescrição penal canônica", () => {
  it("oferece uma única prescrição penal na busca de ferramentas", () => {
    const resultados = buscarFerramentas("prescrição").filter(
      (r) => r.areaSlug === "criminal",
    );
    expect(resultados).toHaveLength(1);
    expect(resultados[0].ferramenta.endpoint).toBe(
      "/penal/ferramentas/prescricao-penal",
    );
  });
});
