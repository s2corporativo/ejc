import { describe, expect, it } from "vitest";
import {
  addCaseContext,
  caseJourneyPath,
  readCaseContext,
} from "./caseContext";

describe("contexto do caso", () => {
  it("abre a jornada do caso recém-criado", () => {
    expect(caseJourneyPath("caso 123")).toBe("/casos/caso%20123/jornada");
  });

  it("lê o caso informado na Central", () => {
    expect(readCaseContext(new URLSearchParams("tipo=prazo&caso=abc"))).toBe(
      "abc",
    );
  });

  it("ignora contexto vazio", () => {
    expect(readCaseContext(new URLSearchParams("caso=%20"))).toBeUndefined();
  });

  it("vincula o payload sem alterar o objeto original", () => {
    const original = { titulo: "Prazo" };
    expect(addCaseContext(original, "caso-1")).toEqual({
      titulo: "Prazo",
      case_id: "caso-1",
    });
    expect(original).toEqual({ titulo: "Prazo" });
  });
});
