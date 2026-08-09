import { describe, expect, it } from "vitest";
import {
  resolverAreaPreferida,
  rotuloAreaPreferida,
} from "./areaPreferida";

describe("Entrada Jurídica — área preferida", () => {
  it("aceita somente classificações canônicas", () => {
    expect(resolverAreaPreferida("ambiental")).toBe("ambiental");
    expect(resolverAreaPreferida("licitacoes")).toBe("licitacoes");
    expect(resolverAreaPreferida("societario")).toBe("societario");
  });

  it("exibe o nome humano da classificação canônica", () => {
    expect(rotuloAreaPreferida("ambiental")).toBe("Direito Ambiental");
    expect(rotuloAreaPreferida("licitacoes")).toBe("Licitações");
  });

  it("ignora slug vazio ou arbitrário", () => {
    expect(resolverAreaPreferida(null)).toBeNull();
    expect(resolverAreaPreferida("")).toBeNull();
    expect(resolverAreaPreferida("constructor")).toBeNull();
    expect(resolverAreaPreferida("area-inventada")).toBeNull();
  });
});
