// Campos mutuamente excludentes: o backend recusa (422) o parâmetro que não
// corresponde à opção escolhida, então campo escondido não pode ser enviado.
import { describe, expect, it } from "vitest";
import {
  campoVisivel,
  camposVisiveis,
  chavesObsoletas,
  paramsVisiveis,
} from "./camposCondicionais";
import { RAMOS, type FerramentaCampo } from "./ramosConfig";

const CAMPOS: FerramentaCampo[] = [
  { nome: "fase", label: "Fase", tipo: "select" },
  {
    nome: "data_notificacao_autuacao",
    label: "Autuação",
    tipo: "date",
    mostrarSe: { campo: "fase", valores: ["defesa_previa"] },
  },
  {
    nome: "data_notificacao_penalidade",
    label: "Penalidade",
    tipo: "date",
    mostrarSe: { campo: "fase", valores: ["jari"] },
  },
  { nome: "valor_multa", label: "Valor", tipo: "number" },
];

describe("camposCondicionais", () => {
  it("campo sem condição é sempre visível", () => {
    expect(campoVisivel(CAMPOS[0], {})).toBe(true);
    expect(campoVisivel(CAMPOS[3], {})).toBe(true);
  });

  it("mostra apenas o campo da opção escolhida", () => {
    const nomes = camposVisiveis(CAMPOS, { fase: "jari" }).map((c) => c.nome);
    expect(nomes).toEqual([
      "fase",
      "data_notificacao_penalidade",
      "valor_multa",
    ]);
  });

  it("sem a opção escolhida, nenhum condicional aparece", () => {
    const nomes = camposVisiveis(CAMPOS, {}).map((c) => c.nome);
    expect(nomes).toEqual(["fase", "valor_multa"]);
  });

  it("não envia valor de campo escondido (evita o 422)", () => {
    const vals = {
      fase: "defesa_previa",
      data_notificacao_autuacao: "2026-01-10",
      // resquício de uma escolha anterior — não pode viajar
      data_notificacao_penalidade: "2026-02-20",
      valor_multa: "",
    };
    expect(paramsVisiveis(CAMPOS, vals)).toEqual({
      fase: "defesa_previa",
      data_notificacao_autuacao: "2026-01-10",
    });
  });

  it("aponta as chaves órfãs para limpeza ao trocar a opção", () => {
    expect(
      chavesObsoletas(CAMPOS, {
        fase: "defesa_previa",
        data_notificacao_penalidade: "2026-02-20",
      }),
    ).toEqual(["data_notificacao_penalidade"]);
    expect(
      chavesObsoletas(CAMPOS, {
        fase: "jari",
        data_notificacao_penalidade: "2026-02-20",
      }),
    ).toEqual([]);
  });
});

describe("ramosConfig — datas excludentes têm mostrarSe", () => {
  // Endpoints cujo handler devolve 422 quando chega data de outra fase/natureza.
  const EXIGEM_CONDICIONAL: Array<[string, string, string[]]> = [
    [
      "transito",
      "prazos-recurso-transito",
      [
        "data_notificacao_autuacao",
        "data_notificacao_penalidade",
        "data_ciencia_decisao_jari",
      ],
    ],
    [
      "administrativo",
      "multa-transito",
      [
        "data_notificacao_autuacao",
        "data_notificacao_penalidade",
        "data_ciencia_decisao_jari",
      ],
    ],
    [
      "previdenciario",
      "prazos-previdenciario",
      ["data_primeiro_pagamento", "data_ciencia_decisao", "data_ajuizamento"],
    ],
  ];

  for (const [ramo, id, campos] of EXIGEM_CONDICIONAL) {
    it(`${ramo}/${id} condiciona as datas excludentes`, () => {
      const ferramenta = RAMOS[ramo].ferramentas.find((f) => f.id === id);
      expect(ferramenta).toBeTruthy();
      for (const nome of campos) {
        const campo = ferramenta?.campos.find((c) => c.nome === nome);
        expect(campo, `campo "${nome}" deve existir`).toBeTruthy();
        expect(
          campo?.mostrarSe,
          `campo "${nome}" precisa de mostrarSe (senão vai junto e dá 422)`,
        ).toBeTruthy();
      }
    });
  }

  it("toda condição aponta para um campo que existe na mesma ferramenta", () => {
    const quebradas = Object.entries(RAMOS).flatMap(([slug, cfg]) =>
      cfg.ferramentas.flatMap((f) =>
        f.campos
          .filter(
            (c) =>
              c.mostrarSe &&
              !f.campos.some((outro) => outro.nome === c.mostrarSe!.campo),
          )
          .map((c) => `${slug}/${f.id}:${c.nome}`),
      ),
    );
    expect(quebradas).toEqual([]);
  });
});
