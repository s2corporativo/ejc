// Contrato ético e de segregação da estimativa de êxito.
//
// A estimativa pode apoiar a análise interna, mas deve permanecer qualificada
// e nunca integrar a superfície do Portal do Cliente.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const SRC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");

function fonte(relativo: string): string {
  return readFileSync(join(SRC_DIR, relativo), "utf-8");
}

function normalizar(source: string): string {
  return source.replace(/\s+/g, " ").trim();
}

const analiseEstrategica = fonte("components/AnaliseEstrategica.tsx");
const entrevistaInteligente = fonte("pages/EntrevistaInteligente.tsx");

const TELAS_PORTAL = [
  "pages/portal/PortalDashboard.tsx",
  "pages/portal/PortalCasos.tsx",
  "pages/portal/PortalCasoDetalhe.tsx",
  "pages/portal/PortalDocumentos.tsx",
  "pages/portal/PortalFinanceiro.tsx",
  "pages/portal/PortalMensagens.tsx",
  "pages/portal/PortalAssinaturas.tsx",
] as const;

describe("governança da estimativa de êxito", () => {
  it("qualifica a métrica interna e afasta promessa ou garantia", () => {
    const source = normalizar(analiseEstrategica);
    expect(source).toContain("Chance de êxito (estimativa interna)");
    expect(source).toContain(
      "Estimativa interna, sujeita à revisão humana. Não constitui promessa ou garantia de resultado.",
    );
  });

  it("mantém a barra acessível como estimativa interna", () => {
    expect(analiseEstrategica).toContain('role="progressbar"');
    expect(analiseEstrategica).toContain(
      'aria-label="Chance de êxito — estimativa interna"',
    );
    expect(analiseEstrategica).toContain("aria-valuemin={0}");
    expect(analiseEstrategica).toContain("aria-valuemax={100}");
    expect(analiseEstrategica).toContain("aria-valuenow={");
  });

  it("preserva a qualificação já existente na Entrevista Inteligente", () => {
    expect(normalizar(entrevistaInteligente)).toContain(
      'label="Chance de êxito (estimativa interna)"',
    );
  });

  for (const tela of TELAS_PORTAL) {
    it(`${tela} não referencia estimativa interna de êxito`, () => {
      expect(fonte(tela)).not.toMatch(
        /chance_sucesso_percent|chance_exito|chance\s+de\s+[êe]xito/i,
      );
    });
  }
});
