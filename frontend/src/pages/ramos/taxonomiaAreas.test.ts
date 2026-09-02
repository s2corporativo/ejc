// Taxonomia de áreas dos hubs (Áreas de Atuação).
//
// O caso criado a partir de um hub precisa nascer com a área DAQUELE hub. Antes
// desta trava, cinco hubs achatavam a área para um valor genérico (bancário,
// imobiliário e trânsito viravam "civil"; LGPD virava "empresarial";
// administrativo virava "tributário") mesmo com o valor correto já existindo no
// enum CaseArea desde a migration 083 — o que contaminava métricas por área,
// jurimetria e a seleção de skills de IA, que roteia por área.
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { RAMOS } from "./ramosConfig";
import { AREAS_FALLBACK } from "../../lib/areaCatalog";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "../../../..");

// Hubs cujo slug difere do valor da área por razão histórica de nomenclatura
// (o enum usa o nome do ramo, o hub usa o adjetivo). Só estes podem divergir.
const SLUG_DIFERENTE_DA_AREA: Record<string, string> = {
  civel: "civil",
  penal: "criminal",
};

const AREAS_CONHECIDAS = new Set(AREAS_FALLBACK.map((a) => a.slug));

function areasCaseBackend(): Set<string> | null {
  const modelo = join(RAIZ, "backend/app/models/case.py");
  if (!existsSync(modelo)) return null; // frontend isolado: nada a comparar
  const fonte = readFileSync(modelo, "utf-8");
  const corpo = fonte.slice(
    fonte.indexOf("class CaseArea"),
    fonte.indexOf("class CaseStatus"),
  );
  return new Set(
    [...corpo.matchAll(/^\s+\w+\s*=\s*"([a-z_]+)"/gm)].map((m) => m[1]),
  );
}

describe("taxonomia de áreas dos hubs", () => {
  it("nenhum hub achata a área: areaCaso corresponde ao próprio hub", () => {
    const divergentes = Object.entries(RAMOS)
      .filter(([slug, cfg]) => {
        const esperada = SLUG_DIFERENTE_DA_AREA[slug] ?? slug;
        return cfg.areaCaso !== esperada;
      })
      .map(([slug, cfg]) => `${slug} → ${cfg.areaCaso}`);
    expect(divergentes).toEqual([]);
  });

  it("toda areaCaso existe no catálogo de áreas", () => {
    const desconhecidas = Object.values(RAMOS)
      .map((cfg) => cfg.areaCaso)
      .filter((area) => !AREAS_CONHECIDAS.has(area));
    expect(desconhecidas).toEqual([]);
  });

  it("as cinco áreas antes achatadas têm hub próprio", () => {
    // Regressão direta do achado: cada uma destas caía em outro valor.
    const esperado: Record<string, string> = {
      bancario: "bancario",
      imobiliario: "imobiliario",
      transito: "transito",
      digital_lgpd: "digital_lgpd",
      administrativo: "administrativo",
    };
    for (const [slug, area] of Object.entries(esperado)) {
      expect(RAMOS[slug], `hub "${slug}" deve existir`).toBeTruthy();
      expect(RAMOS[slug].areaCaso, `hub "${slug}"`).toBe(area);
    }
  });

  it("areasLegadas nunca contém a própria área canônica", () => {
    const invalidos = Object.entries(RAMOS)
      .filter(([, cfg]) => (cfg.areasLegadas ?? []).includes(cfg.areaCaso))
      .map(([slug]) => slug);
    expect(invalidos).toEqual([]);
  });

  it("areasLegadas só aparece nos hubs cuja área foi corrigida", () => {
    const comLegado = Object.entries(RAMOS)
      .filter(([, cfg]) => (cfg.areasLegadas ?? []).length > 0)
      .map(([slug]) => slug)
      .sort();
    expect(comLegado).toEqual([
      "administrativo",
      "bancario",
      "digital_lgpd",
      "imobiliario",
      "transito",
    ]);
  });

  // Trava de drift contra a fonte real: o enum do backend. Se uma área usada
  // pelos hubs não existir lá, o POST /cases falha com 422 em runtime.
  it("toda areaCaso existe no enum CaseArea do backend", () => {
    const doEnum = areasCaseBackend();
    if (!doEnum) return;
    expect(doEnum.size).toBeGreaterThan(0);
    const ausentes = Object.values(RAMOS)
      .map((cfg) => cfg.areaCaso)
      .filter((area) => !doEnum.has(area));
    expect(ausentes).toEqual([]);
  });

  // O fallback existe justamente para o cenário em que GET /areas falha. Nesse
  // estado degradado ele não pode oferecer uma taxonomia menor ou diferente da
  // aceita pelo backend, pois telas distintas acabariam com contratos distintos.
  it("fallback do frontend tem paridade integral com CaseArea do backend", () => {
    const doEnum = areasCaseBackend();
    if (!doEnum) return;
    expect(doEnum.size).toBeGreaterThan(0);
    const doFrontend = new Set(AREAS_FALLBACK.map((area) => area.slug));
    expect([...doFrontend].sort()).toEqual([...doEnum].sort());
  });
});
