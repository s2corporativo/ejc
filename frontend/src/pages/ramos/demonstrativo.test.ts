// O demonstrativo salvo em Peças precisa conter o que a tela mostra: depois da
// Onda 2 o conteúdo vive dentro de arrays/objetos, e o filtro antigo (só
// escalares de 1º nível) produzia peças vazias.
import { describe, expect, it } from "vitest";
import {
  linhasDoResultado,
  rodapeDoResultado,
  provenienciaDoResultado,
} from "./demonstrativo";

describe("linhasDoResultado", () => {
  it("achata arrays de objetos com label hierárquico", () => {
    const res = {
      marcos: [
        {
          evento: "Plano de recuperação",
          prazo: "60 dias",
          data: "2026-03-01",
        },
        { evento: "Assembleia de credores", prazo: "150 dias" },
      ],
    };
    expect(linhasDoResultado(res)).toEqual([
      { label: "Marcos › Plano de recuperação › Prazo", valor: "60 dias" },
      { label: "Marcos › Plano de recuperação › Data", valor: "2026-03-01" },
      { label: "Marcos › Assembleia de credores › Prazo", valor: "150 dias" },
    ]);
  });

  it("achata objetos aninhados (fases da dosimetria)", () => {
    const res = { fase_1: { pena_base_meses: 24, fundamento: "CP art. 59" } };
    expect(linhasDoResultado(res)).toEqual([
      { label: "Fase 1 › Pena Base Meses", valor: "24" },
      { label: "Fase 1 › Fundamento", valor: "CP art. 59" },
    ]);
  });

  it("numera itens de array sem campo identificador", () => {
    expect(
      linhasDoResultado({ requisitos: ["Confissão", "Primariedade"] }),
    ).toEqual([
      { label: "Requisitos › 1", valor: "Confissão" },
      { label: "Requisitos › 2", valor: "Primariedade" },
    ]);
  });

  it("mantém a ordem original, formata booleanos e ignora nulos", () => {
    const res = { expirado: false, dias_restantes: 12, calculo: null };
    expect(linhasDoResultado(res)).toEqual([
      { label: "Expirado", valor: "Não" },
      { label: "Dias Restantes", valor: "12" },
    ]);
  });

  it("não transforma metadados de regra nem avisos em linhas", () => {
    const res = {
      total: 100,
      fontes: ["CPC art. 335"],
      vigencia_regra: "desde 2016",
      versao_regra: "2026.1",
      aviso: "MINUTA",
      homologada: true,
    };
    expect(linhasDoResultado(res)).toEqual([{ label: "Total", valor: "100" }]);
  });
});

describe("rodapeDoResultado", () => {
  it("carrega a fundamentação para a peça salva", () => {
    const rodape = rodapeDoResultado({
      fontes: ["CPC art. 335", "Lei 9.099/95 art. 30"],
      vigencia_regra: "CPC/2015 desde 18/03/2016",
      versao_regra: "2026.1",
      aviso: "MINUTA — revisão humana obrigatória.",
    });
    expect(rodape).toContain("Fontes: CPC art. 335 · Lei 9.099/95 art. 30");
    expect(rodape).toContain("Vigência: CPC/2015 desde 18/03/2016");
    expect(rodape).toContain("Versão da regra: 2026.1");
    expect(rodape).toContain("MINUTA — revisão humana obrigatória.");
  });

  it("aceita fonte/vigencia_tabela no singular (tabelas do tributário)", () => {
    const rodape = rodapeDoResultado({
      fonte: "Res. CGSN 140/2018",
      vigencia_tabela: "2026",
    });
    expect(rodape).toBe("Fontes: Res. CGSN 140/2018\nVigência: 2026");
  });

  it("devolve string vazia sem metadados", () => {
    expect(rodapeDoResultado({ total: 10 })).toBe("");
    expect(rodapeDoResultado(null)).toBe("");
  });
});

// Issue #702 — backend passou a EXIGIR fontes/vigencia_regra/versao_regra no
// corpo de POST /pecas/demonstrativo. Estes testes provam que o frontend
// consegue montar esses campos a partir do que a calculadora já carimba na
// resposta (achado do review Codex: o único chamador real não os enviava).
describe("provenienciaDoResultado", () => {
  it("extrai fontes (array), vigência e versão quando presentes", () => {
    const prov = provenienciaDoResultado({
      total: 100,
      fontes: ["CPC art. 335", "Lei 9.099/95 art. 30"],
      vigencia_regra: "CPC/2015 desde 18/03/2016",
      versao_regra: "2026-07",
    });
    expect(prov).toEqual({
      fontes: ["CPC art. 335", "Lei 9.099/95 art. 30"],
      vigencia_regra: "CPC/2015 desde 18/03/2016",
      versao_regra: "2026-07",
    });
  });

  it("aceita fonte/vigencia_tabela no singular (tabelas do tributário)", () => {
    const prov = provenienciaDoResultado({
      fonte: "Res. CGSN 140/2018",
      vigencia_tabela: "2026",
      versao_regra: "2026-07",
    });
    expect(prov).toEqual({
      fontes: ["Res. CGSN 140/2018"],
      vigencia_regra: "2026",
      versao_regra: "2026-07",
    });
  });

  // Prova por negação — cada um destes é um jeito de a resposta NÃO trazer
  // proveniência suficiente; o chamador precisa bloquear o envio, não mandar
  // string/lista em branco que o backend (Gate de proveniência) rejeitaria.
  it.each([
    ["sem fontes", { vigencia_regra: "vigente", versao_regra: "2026-07" }],
    ["fontes vazia", { fontes: [], vigencia_regra: "vigente", versao_regra: "2026-07" }],
    ["sem vigência", { fontes: ["fonte"], versao_regra: "2026-07" }],
    ["sem versão da regra", { fontes: ["fonte"], vigencia_regra: "vigente" }],
    ["resposta nula", null],
    ["resposta não-objeto", "erro"],
  ])("devolve null quando %s", (_descricao, entrada) => {
    expect(provenienciaDoResultado(entrada)).toBeNull();
  });
});
