// hubDoRamo deve apontar para a rota canônica /areas-de-atuacao/:slug —
// o alias legado /ramos/:slug existe só como redirect (auditoria Onda 1).
import { describe, expect, it } from "vitest";
import { hubDoRamo } from "./RamosHub";
import { CANONICAL_ROUTES } from "../config/canonicalRoutes";
import { RAMOS } from "./ramos/ramosConfig";

describe("hubDoRamo", () => {
  it("gera a rota canônica /areas-de-atuacao/<slug>", () => {
    expect(hubDoRamo("empresarial")).toBe("/areas-de-atuacao/empresarial");
    // Áreas com hub de nome próprio: civil → civel, criminal → penal.
    expect(hubDoRamo("civil")).toBe("/areas-de-atuacao/civel");
    expect(hubDoRamo("criminal")).toBe("/areas-de-atuacao/penal");
  });

  it("nunca gera link pelo alias legado /ramos/", () => {
    for (const slug of Object.keys(RAMOS)) {
      const hub = hubDoRamo(slug);
      expect(hub).not.toMatch(/^\/ramos\//);
      expect(hub?.startsWith(`${CANONICAL_ROUTES.areasAtuacao}/`)).toBe(true);
    }
  });

  it("devolve null para área sem hub", () => {
    expect(hubDoRamo("area-inexistente")).toBeNull();
  });
});
