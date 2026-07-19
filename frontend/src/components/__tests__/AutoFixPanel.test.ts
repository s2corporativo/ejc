import { describe, expect, it } from "vitest";
import { ordenarAchados } from "../AutoFixPanel";

const finding = (
  severidade: "P0" | "P1" | "P2" | "P3" | "INFO",
  titulo: string,
) => ({
  tipo: "teste",
  severidade,
  titulo,
  detalhe: "detalhe",
  sugestao: "sugestão",
  evidencias: [],
  aplicado: false,
  requer_revisao_humana: true,
});

describe("AutoFixPanel", () => {
  it("prioriza P0 antes de P1, P2 e informativos", () => {
    const result = ordenarAchados([
      finding("P2", "Manual"),
      finding("INFO", "Info"),
      finding("P0", "Autenticação"),
      finding("P1", "Colisão"),
    ]);
    expect(result.map((item) => item.severidade)).toEqual([
      "P0",
      "P1",
      "P2",
      "INFO",
    ]);
  });

  it("não altera o array original", () => {
    const original = [finding("P2", "B"), finding("P0", "A")];
    ordenarAchados(original);
    expect(original.map((item) => item.severidade)).toEqual(["P2", "P0"]);
  });
});
