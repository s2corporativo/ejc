// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { respostaListaFoiTruncada } from "./RamoBase";

describe("RamoBase — paginação de casos", () => {
  it("sinaliza quando a API informa total maior que a página carregada", () => {
    expect(respostaListaFoiTruncada({ total: 101 }, 100)).toBe(true);
    expect(respostaListaFoiTruncada({ total: 100 }, 100)).toBe(false);
    expect(respostaListaFoiTruncada({}, 100)).toBe(false);
  });
});
