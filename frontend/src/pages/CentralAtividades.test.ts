import { describe, expect, it } from "vitest";
import { isActivityView } from "./CentralAtividades";

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
