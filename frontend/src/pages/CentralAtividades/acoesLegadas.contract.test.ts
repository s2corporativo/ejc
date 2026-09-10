import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(
  resolve(process.cwd(), "src/pages/CentralAtividades/acoesLegadas.tsx"),
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
    expect(source).toContain("regime_calculo: sim.regime_calculo");
    expect(source).toContain('<option value="civel">Cível — CPC</option>');
    expect(source).toContain(
      '<option value="trabalhista">Trabalhista — CLT</option>',
    );
    expect(source).toContain('<option value="penal">Penal — CPP</option>');
  });

  it("expõe as exceções jurídicas suportadas em vez de fixá-las em false", () => {
    expect(source).toContain("dobro: sim.dobro");
    expect(source).toContain(
      "excecao_recesso_penal: sim.excecao_recesso_penal",
    );
    expect(source).toContain("Aplicar contagem em dobro.");
    expect(source).toContain("Aplicar exceção ao recesso do CPP art. 798-A.");
    expect(source).not.toContain("dobro: false,\n        tribunal:");
    expect(source).not.toContain("excecao_recesso_penal: false,\n      });");
  });

  it("mantém revisão humana obrigatória para todo resultado calculado", () => {
    expect(source).toContain("Revisão humana obrigatória — confira publicação");
    expect(source).toContain("Resultado preliminar/degradado");
    expect(source).toContain("res.revisao_obrigatoria");
    expect(source).toContain("deve sempre ser");
  });

  it("exibe snapshot do motor e fontes oficiais por regime", () => {
    expect(source).toContain('versaoMotor: "prazos-2026-09-10"');
    expect(source).toContain('fonteConsultadaEm: "10/09/2026"');
    expect(source).toContain("l13105.htm");
    expect(source).toContain("del5452.htm");
    expect(source).toContain("del3689compilado.htm");
    expect(source).toContain("Abrir texto oficial no Planalto");
    expect(source).toContain("Regra aplicada pelo motor:");
  });
});
