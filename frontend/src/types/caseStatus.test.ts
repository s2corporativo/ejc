import { describe, expect, it } from "vitest";

import {
  CASE_STATUS,
  CASE_STATUS_ABERTOS,
  CASE_STATUS_FECHADOS,
  isCaseStatus,
  isCasoAtivo,
} from "./caseStatus";

describe("caseStatus", () => {
  it("classifica somente os quatro status canônicos abertos como ativos", () => {
    for (const status of CASE_STATUS_ABERTOS) {
      expect(isCasoAtivo(status)).toBe(true);
    }

    for (const status of CASE_STATUS_FECHADOS) {
      expect(isCasoAtivo(status)).toBe(false);
    }
  });

  it("falha fechada para status desconhecido, vazio ou ausente", () => {
    for (const status of ["cancelado", "inativo", "em_andamento", "", null, undefined]) {
      expect(isCasoAtivo(status)).toBe(false);
    }
  });

  it("mantém os conjuntos abertos e fechados como partição exata do enum", () => {
    const classificados = new Set([
      ...CASE_STATUS_ABERTOS,
      ...CASE_STATUS_FECHADOS,
    ]);

    expect(classificados.size).toBe(CASE_STATUS.length);
    expect([...classificados].sort()).toEqual([...CASE_STATUS].sort());
    expect(CASE_STATUS_ABERTOS.filter((status) => CASE_STATUS_FECHADOS.includes(status))).toEqual([]);
  });

  it("reconhece somente valores persistidos pelo backend", () => {
    for (const status of CASE_STATUS) {
      expect(isCaseStatus(status)).toBe(true);
    }

    expect(isCaseStatus("cancelado")).toBe(false);
    expect(isCaseStatus(null)).toBe(false);
  });
});
