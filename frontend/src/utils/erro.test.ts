import { describe, expect, it } from "vitest";

import {
  dadosErro,
  detalheBruto,
  detalheErro,
  foiAbortado,
  mensagemErro,
  statusErro,
} from "./erro";

const FALLBACK = "Falha ao executar a operação.";

function comDetail(detail: unknown) {
  return { response: { data: { detail } } };
}

describe("detalheErro", () => {
  it("devolve a string de detail quando o backend manda mensagem simples", () => {
    expect(detalheErro(comDetail("Caso não encontrado."), FALLBACK)).toBe(
      "Caso não encontrado.",
    );
  });

  it("cai no fallback quando detail é string vazia", () => {
    expect(detalheErro(comDetail(""), FALLBACK)).toBe(FALLBACK);
  });

  it("lê a chave mensagem quando detail é objeto", () => {
    expect(
      detalheErro(comDetail({ mensagem: "Prazo já confirmado." }), FALLBACK),
    ).toBe("Prazo já confirmado.");
  });

  it("junta as mensagens do 422 do Pydantic", () => {
    const detail = [
      { loc: ["body", "cpf"], msg: "CPF inválido" },
      { loc: ["body", "nome"], msg: "campo obrigatório" },
    ];
    expect(detalheErro(comDetail(detail), FALLBACK)).toBe(
      "CPF inválido; campo obrigatório",
    );
  });

  it("aceita lista de strings", () => {
    expect(detalheErro(comDetail(["erro A", "erro B"]), FALLBACK)).toBe(
      "erro A; erro B",
    );
  });

  it("cai no fallback quando a lista não tem mensagem aproveitável", () => {
    expect(detalheErro(comDetail([{ loc: ["body"] }]), FALLBACK)).toBe(
      FALLBACK,
    );
  });

  it("cai no fallback para objeto sem mensagem", () => {
    expect(detalheErro(comDetail({ codigo: 42 }), FALLBACK)).toBe(FALLBACK);
  });

  it("cai no fallback para erro que não veio da API", () => {
    expect(detalheErro(new Error("boom"), FALLBACK)).toBe(FALLBACK);
    expect(detalheErro(undefined, FALLBACK)).toBe(FALLBACK);
    expect(detalheErro(null, FALLBACK)).toBe(FALLBACK);
  });

  it("cai no fallback quando detail é só espaço em branco", () => {
    // Vinha do `erroDetalhe` de acoesLegadas.tsx, a única cópia que fazia trim.
    expect(detalheErro(comDetail("   "), FALLBACK)).toBe(FALLBACK);
  });

  it("lê a chave message, não só mensagem", () => {
    // Vinha das cópias de LoginModern.tsx e Configurar2FA.tsx.
    expect(
      detalheErro(comDetail({ message: "TOTP obrigatório" }), FALLBACK),
    ).toBe("TOTP obrigatório");
  });

  it("não despeja JSON cru na tela para objeto sem mensagem", () => {
    // As cópias `errDetail` devolviam JSON.stringify(detail).slice(0,200), o que
    // colocava `{"campo":"cpf","codigo":422}` dentro de um toast para o usuário.
    expect(
      detalheErro(comDetail({ campo: "cpf", codigo: 422 }), FALLBACK),
    ).toBe(FALLBACK);
  });
});

describe("statusErro", () => {
  it("lê o status HTTP da resposta", () => {
    expect(statusErro({ response: { status: 403 } })).toBe(403);
  });

  it("devolve undefined para erro sem resposta HTTP", () => {
    expect(statusErro(new Error("rede"))).toBeUndefined();
    expect(statusErro({ response: { status: "403" } })).toBeUndefined();
    expect(statusErro(null)).toBeUndefined();
  });
});

describe("mensagemErro", () => {
  it("lê message de erro nativo", () => {
    expect(mensagemErro(new Error("conexão perdida"), FALLBACK)).toBe(
      "conexão perdida",
    );
  });

  it("cai no fallback sem message utilizável", () => {
    expect(mensagemErro({ message: "" }, FALLBACK)).toBe(FALLBACK);
    expect(mensagemErro({}, FALLBACK)).toBe(FALLBACK);
  });
});

describe("foiAbortado", () => {
  it("reconhece as quatro formas de cancelamento", () => {
    expect(foiAbortado({ name: "AbortError" })).toBe(true);
    expect(foiAbortado({ name: "CanceledError" })).toBe(true);
    expect(foiAbortado({ name: "TimeoutError" })).toBe(true);
    expect(foiAbortado({ code: "ERR_CANCELED" })).toBe(true);
  });

  it("não confunde falha real com cancelamento", () => {
    expect(foiAbortado(new Error("500"))).toBe(false);
    expect(foiAbortado({ response: { status: 500 } })).toBe(false);
    expect(foiAbortado(null)).toBe(false);
    expect(foiAbortado(undefined)).toBe(false);
  });
});

describe("dadosErro e detalheBruto", () => {
  it("dadosErro devolve response.data para sinalização fora do detail", () => {
    const erro = { response: { data: { must_change_password: true } } };
    expect(dadosErro(erro)?.must_change_password).toBe(true);
  });

  it("dadosErro devolve undefined quando data não é objeto", () => {
    expect(dadosErro({ response: { data: "erro" } })).toBeUndefined();
    expect(dadosErro(new Error("x"))).toBeUndefined();
  });

  it("detalheBruto preserva a forma do payload", () => {
    const pendencias = { pendencias: ["falta o CPF"] };
    expect(detalheBruto(comDetail(pendencias))).toEqual(pendencias);
    expect(detalheBruto(new Error("x"))).toBeUndefined();
  });
});
