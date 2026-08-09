import { describe, expect, it } from "vitest";
import { hubDoRamo } from "./RamosHub";
import { CANONICAL_ROUTES } from "../config/canonicalRoutes";
import { RAMOS } from "./ramos/ramosConfig";

describe("hubDoRamo", () => {
  it("gera a rota canônica para os workspaces operacionais", () => {
    expect(hubDoRamo("empresarial")).toBe("/areas-de-atuacao/empresarial");
    expect(hubDoRamo("civil")).toBe("/areas-de-atuacao/civel");
    expect(hubDoRamo("criminal")).toBe("/areas-de-atuacao/penal");
  });

  it("leva especialidades subordinadas ao workspace do núcleo sem reclassificar casos", () => {
    expect(hubDoRamo("societario")).toBe("/areas-de-atuacao/empresarial");
    expect(hubDoRamo("sucessoes")).toBe("/areas-de-atuacao/familia");
    expect(hubDoRamo("licitacoes")).toBe("/areas-de-atuacao/administrativo");
  });

  it("nunca gera link pelo alias legado /ramos/", () => {
    for (const slug of Object.keys(RAMOS)) {
      const hub = hubDoRamo(slug);
      expect(hub).not.toMatch(/^\/ramos\//);
      expect(hub?.startsWith(`${CANONICAL_ROUTES.areasAtuacao}/`)).toBe(true);
    }
  });

  it("devolve null para área sem workspace próprio ou núcleo seguro", () => {
    expect(hubDoRamo("area-inexistente")).toBeNull();
    expect(hubDoRamo("internacional")).toBeNull();
  });
});
