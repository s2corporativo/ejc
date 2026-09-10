import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const source = readFileSync(
  new URL("./acoesLegadas.tsx", import.meta.url),
  "utf8",
);

describe("Central de Atividades — contratos jurídicos de prazo", () => {
  it("envia vencimento conferido ao aceitar prazo DJEN", () => {
    expect(source).toContain("/aceitar-prazo");
    expect(source).toContain("{ data_prazo: dataPrazo }");
    expect(source).toContain("Vencimento conferido *");
  });

  it("usa somente o motor canônico de cálculo para o simulador", () => {
    expect(source).toContain('api.post("/deadlines/calcular"');
    expect(source).not.toContain('api.post("/suspensoes/simular"');
    expect(source).toContain('regime_calculo: sim.regime_calculo');
    expect(source).toContain('<option value="civel">Cível — CPC</option>');
    expect(source).toContain('<option value="trabalhista">Trabalhista — CLT</option>');
    expect(source).toContain('<option value="penal">Penal — CPP</option>');
  });

  it("expõe ao usuário quando o cálculo exige revisão humana", () => {
    expect(source).toContain("res.revisao_obrigatoria");
    expect(source).toContain("Resultado preliminar — revisão humana obrigatória.");
  });
});
