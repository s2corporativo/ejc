import { describe, expect, it } from "vitest";
import { isSocietyTab } from "./Sociedade";

describe("Sociedade deep links", () => {
  it.each(["socios", "distribuicao", "saques"])(
    "aceita a subaba %s",
    (tab) => {
      expect(isSocietyTab(tab)).toBe(true);
    },
  );

  it("rejeita subaba desconhecida ou ausente", () => {
    expect(isSocietyTab("retiradas-antigas")).toBe(false);
    expect(isSocietyTab(null)).toBe(false);
  });
});
