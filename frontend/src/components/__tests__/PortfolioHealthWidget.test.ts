import { describe, expect, it } from "vitest";
import {
  detalheErroCarteira,
  ordenarCarteira,
  principalMotivo,
  type PortfolioCase,
} from "../portfolioHealthModel";

function item(
  id: string,
  score: number,
  overdue: number,
  inactiveDays: number,
): PortfolioCase {
  return {
    id,
    titulo: id,
    inactive_days: inactiveDays,
    score,
    level: score < 40 ? "critical" : score < 65 ? "risk" : "attention",
    metrics: {
      actionable_tasks: 0,
      overdue_deadlines: overdue,
      deadlines_next_3_days: 0,
    },
    indicators: [],
    next_recommended_action: "Revisar o caso",
    route: `/casos/${id}`,
  };
}

describe("PortfolioHealthWidget — regras puras", () => {
  it("ordena por score, prazo vencido e inatividade sem alterar a entrada", () => {
    const original = [
      item("B", 50, 0, 50),
      item("A", 30, 0, 5),
      item("C", 50, 2, 2),
    ];
    const ordered = ordenarCarteira(original);
    expect(ordered.map((entry) => entry.id)).toEqual(["A", "C", "B"]);
    expect(original.map((entry) => entry.id)).toEqual(["B", "A", "C"]);
  });

  it("usa o primeiro indicador e preserva a próxima ação como fallback", () => {
    const withIndicator = item("A", 30, 1, 10);
    withIndicator.indicators = [
      {
        code: "OVERDUE_DEADLINES",
        severity: "critical",
        message: "Há prazo vencido.",
        recommended_action: "Regularizar.",
      },
    ];
    expect(principalMotivo(withIndicator)).toBe("Há prazo vencido.");
    expect(principalMotivo(item("B", 70, 0, 0))).toBe("Revisar o caso");
  });

  it("aceita o contrato actionables/score/level e não o vocabulário antigo", () => {
    const current = item("A", 42, 1, 30);
    expect(current.score).toBe(42);
    expect(current.level).toBe("risk");
    expect(current.metrics.actionable_tasks).toBe(0);
    expect("health_score" in current).toBe(false);
    expect("pending_tasks" in current.metrics).toBe(false);
  });

  it("preserva detalhe textual do backend", () => {
    expect(
      detalheErroCarteira({ response: { data: { detail: "Acesso negado" } } }),
    ).toBe("Acesso negado");
    expect(detalheErroCarteira(new Error("falha"))).toContain(
      "Não foi possível carregar",
    );
  });
});
