import { describe, expect, it } from "vitest";
import { formatarDataEvento, ordenarIndicadores } from "../CaseHealthWidget";

describe("CaseHealthWidget — regras puras", () => {
  it("ordena indicadores por severidade operacional", () => {
    const result = ordenarIndicadores([
      {
        code: "LOW",
        severity: "low",
        message: "Informativo",
        recommended_action: "Revisar",
      },
      {
        code: "CRITICAL",
        severity: "critical",
        message: "Crítico",
        recommended_action: "Agir agora",
      },
      {
        code: "HIGH",
        severity: "high",
        message: "Alto",
        recommended_action: "Priorizar",
      },
    ]);
    expect(result.map((item) => item.code)).toEqual([
      "CRITICAL",
      "HIGH",
      "LOW",
    ]);
  });

  it("não altera o array recebido ao ordenar", () => {
    const original = [
      {
        code: "LOW",
        severity: "low" as const,
        message: "Informativo",
        recommended_action: "Revisar",
      },
      {
        code: "HIGH",
        severity: "high" as const,
        message: "Alto",
        recommended_action: "Priorizar",
      },
    ];
    ordenarIndicadores(original);
    expect(original.map((item) => item.code)).toEqual(["LOW", "HIGH"]);
  });

  it("trata datas inválidas de forma honesta", () => {
    expect(formatarDataEvento("valor-invalido")).toBe("Data não informada");
  });
});
