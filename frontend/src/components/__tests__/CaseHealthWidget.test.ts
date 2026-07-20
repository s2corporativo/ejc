import { describe, expect, it } from "vitest";
import {
  detalheErroSaude,
  formatarDataEvento,
  ordenarIndicadores,
} from "../caseHealthModel";

describe("CaseHealthWidget — regras puras", () => {
  it("ordena indicadores por severidade sem alterar o array recebido", () => {
    const original = [
      {
        code: "LOW",
        severity: "low" as const,
        message: "Informativo",
        recommended_action: "Revisar",
      },
      {
        code: "CRITICAL",
        severity: "critical" as const,
        message: "Crítico",
        recommended_action: "Agir agora",
      },
      {
        code: "HIGH",
        severity: "high" as const,
        message: "Alto",
        recommended_action: "Priorizar",
      },
    ];
    const result = ordenarIndicadores(original);
    expect(result.map((item) => item.code)).toEqual([
      "CRITICAL",
      "HIGH",
      "LOW",
    ]);
    expect(original.map((item) => item.code)).toEqual([
      "LOW",
      "CRITICAL",
      "HIGH",
    ]);
  });

  it("trata datas inválidas de forma honesta", () => {
    expect(formatarDataEvento("valor-invalido")).toBe("Data não informada");
  });

  it("preserva mensagem estruturada do backend", () => {
    expect(
      detalheErroSaude({
        response: { data: { detail: { mensagem: "Caso inacessível" } } },
      }),
    ).toBe("Caso inacessível");
    expect(detalheErroSaude(new Error("falha"))).toContain(
      "Não foi possível carregar",
    );
  });
});
