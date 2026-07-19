import { describe, expect, it } from "vitest";
import { AREAS_FALLBACK, areaLabel } from "./areaCatalog";

describe("taxonomia canônica de áreas", () => {
  it("mantém as 25 áreas do backend como fallback", () => {
    expect(AREAS_FALLBACK).toHaveLength(25);
    expect(new Set(AREAS_FALLBACK.map((area) => area.slug)).size).toBe(25);
  });

  it("apresenta rótulos amigáveis", () => {
    expect(areaLabel("digital_lgpd")).toBe("Digital e LGPD");
    expect(areaLabel("licitacoes")).toBe("Licitações");
  });
});
