import { describe, expect, it } from "vitest";
import { STAFF_ROUTES } from "../config/moduleRegistry";
import { CATEGORIAS_FERRAMENTAS } from "./Ferramentas";

describe("Mais Ferramentas — catálogo canônico", () => {
  it("não referencia chaves de módulos inexistentes", () => {
    const registradas = new Set(STAFF_ROUTES.map((route) => route.key));
    const catalogadas = CATEGORIAS_FERRAMENTAS.flatMap((group) => group.keys);
    for (const key of catalogadas) {
      expect(registradas.has(key), `chave órfã no catálogo: ${key}`).toBe(true);
    }
  });

  it("cataloga TODO módulo de topo oculto do menu", () => {
    // Módulo de topo = rota de um único segmento, sem parâmetro (as rotas de
    // detalhe, ex. /casos/:id, são ocultas por natureza e não são "ferramenta").
    // `ajuda` era o único que faltava: só se chegava a ele pelo HelpButton.
    const catalogadas = new Set(
      CATEGORIAS_FERRAMENTAS.flatMap((group) => group.keys),
    );
    const ocultosDeTopo = STAFF_ROUTES.filter(
      (route) =>
        route.status === "hidden" &&
        !route.path.includes(":") &&
        !route.path.includes("*") &&
        route.path.split("/").filter(Boolean).length === 1,
    );
    expect(ocultosDeTopo.length).toBeGreaterThan(10);
    for (const route of ocultosDeTopo) {
      expect(
        catalogadas.has(route.key),
        `módulo oculto sem cartão em /ferramentas: ${route.key}`,
      ).toBe(true);
    }
  });

  it("dá a /cadastro-manual o único ponto de entrada do app", () => {
    // A rota é viva (registrada, com RBAC e componente em uso pela Entrada
    // Única em modo manual) e não tinha nenhum link em src/.
    const catalogadas = CATEGORIAS_FERRAMENTAS.flatMap((group) => group.keys);
    expect(catalogadas).toContain("cadastro-manual");
    expect(STAFF_ROUTES.some((route) => route.key === "cadastro-manual")).toBe(
      true,
    );
  });

  it("usa apenas a chave consolidada do Radar", () => {
    const keys = CATEGORIAS_FERRAMENTAS.flatMap((group) => group.keys);
    expect(keys).toContain("radar");
    expect(keys).not.toContain("radar-compliance");
    expect(keys).not.toContain("radar-regulatorio");
  });
});
