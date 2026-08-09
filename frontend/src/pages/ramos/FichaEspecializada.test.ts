import { describe, expect, it } from "vitest";
import { valorObrigatorioAusente } from "./FichaEspecializada";

describe("FichaEspecializada — campos obrigatórios", () => {
  it("considera ausentes apenas undefined, null e string vazia", () => {
    expect(valorObrigatorioAusente(undefined)).toBe(true);
    expect(valorObrigatorioAusente(null)).toBe(true);
    expect(valorObrigatorioAusente("")).toBe(true);
  });

  it("preserva zero e false como valores válidos", () => {
    expect(valorObrigatorioAusente(0)).toBe(false);
    expect(valorObrigatorioAusente(false)).toBe(false);
  });
});
