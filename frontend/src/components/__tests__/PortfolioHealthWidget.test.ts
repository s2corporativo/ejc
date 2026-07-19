import { describe, expect, it } from "vitest";
import {
  ordenarCarteira,
  principalMotivo,
} from "../PortfolioHealthWidget";

const base = {
  id: "case-1",
  titulo: "Caso",
  area: "civil",
  prioridade: "media",
  last_activity_at: "2026-07-19T10:00:00Z",
  inactive_days: 0,
  pending_tasks: 1,
  overdue_deadlines: 0,
  deadlines_next_3_days: 0,
  overdue_client_requests: 0,
  active_processes: 1,
  unreviewed_ai_documents: 0,
  documents_in_review: 0,
  health_score: 90,
  health_level: "healthy" as const,
  route: "/casos/case-1",
};

describe("PortfolioHealthWidget — regras puras", () => {
  it("prioriza menor score e, no empate, maior número de prazos vencidos", () => {
    const items = ordenarCarteira([
      { ...base, id: "healthy", health_score: 90 },
      {
        ...base,
        id: "risk-1",
        health_score: 40,
        health_level: "risk",
        overdue_deadlines: 1,
      },
      {
        ...base,
        id: "risk-3",
        health_score: 40,
        health_level: "risk",
        overdue_deadlines: 3,
      },
    ]);
    expect(items.map((item) => item.id)).toEqual([
      "risk-3",
      "risk-1",
      "healthy",
    ]);
  });

  it("explica o principal motivo em ordem de criticidade", () => {
    expect(
      principalMotivo({
        ...base,
        overdue_deadlines: 2,
        overdue_client_requests: 3,
      }),
    ).toBe("2 prazo(s) vencido(s)");
    expect(principalMotivo({ ...base, deadlines_next_3_days: 1 })).toBe(
      "1 prazo(s) nos próximos 3 dias",
    );
    expect(principalMotivo({ ...base, pending_tasks: 0 })).toBe(
      "Caso ativo sem próxima tarefa",
    );
  });

  it("não altera o array original ao ordenar", () => {
    const original = [
      { ...base, id: "a", health_score: 80 },
      { ...base, id: "b", health_score: 30 },
    ];
    ordenarCarteira(original);
    expect(original.map((item) => item.id)).toEqual(["a", "b"]);
  });
});
