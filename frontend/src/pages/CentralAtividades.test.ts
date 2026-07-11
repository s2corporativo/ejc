import { describe, expect, it } from "vitest";
import { isActivityView } from "./CentralAtividades";
import { isCentralTab } from "./Central";

describe("Central unificada deep links", () => {
  it.each(["atividades", "relacionamento"])("aceita a aba %s", (tab) => {
    expect(isCentralTab(tab)).toBe(true);
  });

  it("rejeita aba desconhecida ou ausente (cai em atividades)", () => {
    expect(isCentralTab("crm")).toBe(false);
    expect(isCentralTab(null)).toBe(false);
  });
});

describe("CentralAtividades deep links", () => {
  it.each(["lista", "calendario", "timeline", "kanban"])(
    "aceita a visualização %s",
    (view) => {
      expect(isActivityView(view)).toBe(true);
    },
  );

  it("rejeita visualização desconhecida ou ausente", () => {
    expect(isActivityView("agenda-antiga")).toBe(false);
    expect(isActivityView(null)).toBe(false);
  });
});
