// A aba "Ferramentas" do caso resolve os ramos pela área do caso. Antes isso
// era um mapa manual que só conhecia as áreas antigas: quando a taxonomia
// deixou de achatar bancário/imobiliário/trânsito/LGPD/administrativo, um caso
// novo criado nesses hubs chegava ao detalhe e a aba não renderizava NENHUMA
// calculadora. Agora o mapa é derivado de RAMOS — estes testes travam isso.
import { describe, expect, it } from "vitest";
import { RAMOS, ramosDaArea } from "./ramosConfig";

// Hubs cuja área deixou de ser achatada (Onda de taxonomia) + a área legada
// com que os casos históricos foram gravados.
const HUBS_CORRIGIDOS: Array<[string, string]> = [
  ["bancario", "civil"],
  ["imobiliario", "civil"],
  ["transito", "civil"],
  ["digital_lgpd", "empresarial"],
  ["administrativo", "tributario"],
];

describe("ramosDaArea", () => {
  it("toda área canônica de hub resolve ao menos um ramo com ferramentas", () => {
    const vazias = Object.values(RAMOS)
      .filter((cfg) => cfg.ferramentas.length > 0)
      .map((cfg) => cfg.areaCaso)
      .filter((area) => ramosDaArea(area).length === 0);
    expect(vazias).toEqual([]);
  });

  for (const [slug, legada] of HUBS_CORRIGIDOS) {
    it(`caso novo do hub "${slug}" enxerga as ferramentas do próprio ramo`, () => {
      const area = RAMOS[slug].areaCaso;
      const resolvidos = ramosDaArea(area);
      expect(resolvidos.map((c) => c.slug)).toContain(slug);
      // O ramo do próprio hub vem primeiro (é a aba aberta por padrão).
      expect(resolvidos[0].slug).toBe(slug);
      expect(resolvidos[0].ferramentas.length).toBeGreaterThan(0);
    });

    it(`caso histórico em "${legada}" continua enxergando o ramo "${slug}"`, () => {
      expect(ramosDaArea(legada).map((c) => c.slug)).toContain(slug);
    });
  }

  it("área desconhecida ou vazia devolve lista vazia, sem quebrar", () => {
    expect(ramosDaArea("area_inexistente")).toEqual([]);
    expect(ramosDaArea(undefined)).toEqual([]);
    expect(ramosDaArea("")).toEqual([]);
  });

  it("nunca devolve ramo sem ferramentas (não há aba vazia)", () => {
    const areas = new Set(
      Object.values(RAMOS).flatMap((cfg) => [
        cfg.areaCaso,
        ...(cfg.areasLegadas ?? []),
      ]),
    );
    for (const area of areas) {
      for (const cfg of ramosDaArea(area)) {
        expect(cfg.ferramentas.length, `${area} → ${cfg.slug}`).toBeGreaterThan(
          0,
        );
      }
    }
  });
});
