import { describe, expect, it } from "vitest";
import { isFinanceTab, nextFinanceParams } from "./FinanceiroWorkspace";

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
});
