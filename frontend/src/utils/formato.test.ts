import { describe, expect, it } from "vitest";
import { fmtDate, fmtDateTime, fmtMoney } from "./formato";

// toLocaleString pt-BR separa "R$" do número com NBSP (ou NNBSP conforme a
// versão do ICU) — normaliza para espaço comum antes de comparar.
const plain = (s: string) => s.replace(/[\u00a0\u202f]/g, " ");

describe("fmtMoney", () => {
  it("formata em Reais com 2 casas por padrão", () => {
    expect(plain(fmtMoney(1234.5))).toBe("R$ 1.234,50");
  });

  it("respeita casasMax para valores de alta precisão", () => {
    expect(plain(fmtMoney(0.1234, 4))).toBe("R$ 0,1234");
    // mínimo de 2 casas é preservado mesmo com casasMax maior
    expect(plain(fmtMoney(10, 4))).toBe("R$ 10,00");
  });

  it("devolve travessão para vazio/NaN", () => {
    expect(fmtMoney(null)).toBe("—");
    expect(fmtMoney(undefined)).toBe("—");
    expect(fmtMoney(Number.NaN)).toBe("—");
  });
});

describe("fmtDate", () => {
  it("formata dd/mm/aaaa", () => {
    expect(fmtDate("2026-07-26T15:00:00")).toBe("26/07/2026");
  });

  it("ancora data pura ao meio-dia (sem recuo por fuso)", () => {
    expect(fmtDate("2026-07-26")).toBe("26/07/2026");
  });

  it("devolve travessão para vazio", () => {
    expect(fmtDate(null)).toBe("—");
    expect(fmtDate("")).toBe("—");
  });
});

describe("fmtDateTime", () => {
  it("formata data e hora curtas", () => {
    expect(fmtDateTime("2026-07-26T09:05:00")).toMatch(
      /^26\/07\/2026,? 09:05$/,
    );
  });

  it("devolve o fallback para vazio/inválido", () => {
    expect(fmtDateTime(undefined)).toBe("—");
    expect(fmtDateTime("xx", "Data indisponível")).toBe("Data indisponível");
  });
});
