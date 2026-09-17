// Contrato do formulário de encerramento com o backend.
//
// Regressão: o select de resultado oferecia "exito_total" e "improcedente" —
// valores que EncerrarCasoReq (backend/app/routers/cases.py) rejeita por
// regex. Como "exito_total" era ainda o default do formulário, encerrar um
// caso pela tela devolvia 422 sem que nada na tela explicasse o motivo.
// Falha se a UI voltar a divergir do vocabulário canônico do backend.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const FONTE = readFileSync(
  resolve(process.cwd(), "src/pages/CasoDetalhe/TabResumo.tsx"),
  "utf8",
);

// Espelha o pattern de EncerrarCasoReq.resultado.
const RESULTADOS_CANONICOS = [
  "exito",
  "exito_parcial",
  "acordo",
  "derrota",
  "desistencia",
  "arquivado",
];

// Vocabulário de RESULTADO (as demais listas da tela têm domínio próprio).
const DOMINIO_RESULTADO =
  /^(exito|exito_total|exito_parcial|acordo|derrota|desistencia|arquivado|improcedente|procedente)$/;

describe("Encerramento do caso — contrato com o backend", () => {
  const resultadosOferecidos = [...FONTE.matchAll(/<option value="([^"]+)">/g)]
    .map((m) => m[1])
    .filter((v) => DOMINIO_RESULTADO.test(v));

  it("todo resultado oferecido é aceito pelo backend", () => {
    expect(resultadosOferecidos.length).toBeGreaterThan(0);
    expect(
      resultadosOferecidos.filter((v) => !RESULTADOS_CANONICOS.includes(v)),
    ).toEqual([]);
  });

  it("o default do formulário é um resultado aceito", () => {
    const m = FONTE.match(/resultado:\s*"([^"]+)"/);
    expect(m).not.toBeNull();
    expect(RESULTADOS_CANONICOS).toContain(m![1]);
  });

  it("o encerramento oferece a sincronização com o tribunal", () => {
    expect(FONTE).toContain("sincronizar_processo_eletronico");
    expect(FONTE).toMatch(/PJe|MNI/);
  });
});
