import { describe, expect, it } from "vitest";
import {
  competenciaAtual,
  isCompetencia,
  isFinanceTab,
  nextFinanceParams,
} from "./FinanceiroWorkspace";

describe("FinanceiroWorkspace deep links", () => {
  it.each([
    "visao",
    "honorarios",
    "despesas",
    "recorrentes",
    "contratos",
    "societaria",
    "estimador",
  ])("aceita a aba %s", (tab) => {
    expect(isFinanceTab(tab)).toBe(true);
  });

  it("preserva a subaba ao permanecer na gestão societária", () => {
    const current = new URLSearchParams("tab=societaria&sub=saques");
    const next = nextFinanceParams(current, "societaria");
    expect(next.get("tab")).toBe("societaria");
    expect(next.get("sub")).toBe("saques");
  });

  it("remove a subaba societária ao trocar de módulo financeiro", () => {
    const current = new URLSearchParams("tab=societaria&sub=saques");
    const next = nextFinanceParams(current, "contratos");
    expect(next.get("tab")).toBe("contratos");
    expect(next.has("sub")).toBe(false);
  });

  it("limpa o filtro de status de drill-down ao trocar de aba", () => {
    const current = new URLSearchParams("tab=honorarios&status=pendente");
    const next = nextFinanceParams(current, "contratos");
    expect(next.has("status")).toBe(false);
  });

  it("aplica o status do drill-down na aba de destino", () => {
    const current = new URLSearchParams("tab=visao&comp=2026-07");
    const next = nextFinanceParams(current, "honorarios", {
      status: "pendente",
    });
    expect(next.get("tab")).toBe("honorarios");
    expect(next.get("status")).toBe("pendente");
    // competência compartilhada é preservada entre abas
    expect(next.get("comp")).toBe("2026-07");
  });
});

describe("competência compartilhada", () => {
  it.each(["2026-01", "2025-12", "1999-07"])("aceita %s", (v) => {
    expect(isCompetencia(v)).toBe(true);
  });

  it.each([null, "", "2026", "2026-13", "2026-00", "07-2026", "2026-7"])(
    "rejeita %s",
    (v) => {
      expect(isCompetencia(v)).toBe(false);
    },
  );

  it("competenciaAtual devolve o mês corrente em AAAA-MM", () => {
    const now = new Date();
    const esperado = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    expect(competenciaAtual()).toBe(esperado);
    expect(isCompetencia(competenciaAtual())).toBe(true);
  });
});
