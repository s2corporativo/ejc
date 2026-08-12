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

  it("usa apenas a chave consolidada do Radar", () => {
    const keys = CATEGORIAS_FERRAMENTAS.flatMap((group) => group.keys);
    expect(keys).toContain("radar");
    expect(keys).not.toContain("radar-compliance");
    expect(keys).not.toContain("radar-regulatorio");
  });
});
