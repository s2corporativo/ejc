import { describe, expect, it } from "vitest";
import {
  addCaseContext,
  caseJourneyPath,
  caseTabPath,
  readCaseContext,
} from "./caseContext";

describe("contexto do caso", () => {
  it("abre a visão canônica do caso recém-criado", () => {
    expect(caseJourneyPath("caso 123")).toBe(
      "/casos/caso%20123?tab=resumo",
    );
  });

  it("gera deep-link de aba sem perder encoding do caso", () => {
    expect(caseTabPath("caso 123", "peças especiais")).toBe(
      "/casos/caso%20123?tab=pe%C3%A7as%20especiais",
    );
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
