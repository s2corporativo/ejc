import { describe, expect, it } from "vitest";

import { detalheErro } from "./erro";

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
});
