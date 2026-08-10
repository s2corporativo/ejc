import { describe, expect, it } from "vitest";
import { mensagemErroHttp } from "./iaErro";
import { LatestRequestGate } from "./latestRequest";

describe("LatestRequestGate", () => {
  it("aceita somente a geração mais recente", () => {
    const gate = new LatestRequestGate();
    const primeira = gate.begin();
    const segunda = gate.begin();

    expect(gate.isCurrent(primeira)).toBe(false);
    expect(gate.isCurrent(segunda)).toBe(true);
  });

  it("invalidate torna a resposta corrente obsoleta", () => {
    const gate = new LatestRequestGate();
    const token = gate.begin();
    gate.invalidate();

    expect(gate.isCurrent(token)).toBe(false);
  });
});

describe("mensagemErroHttp", () => {
  it("aceita detail string seguro", () => {
    expect(
      mensagemErroHttp(
        { response: { data: { detail: "Conclua a conferência antes de seguir" } } },
        "fallback",
      ),
    ).toBe("Conclua a conferência antes de seguir");
  });

  it("aceita somente mensagem conhecida em detail objeto", () => {
    expect(
      mensagemErroHttp(
        {
          response: {
            data: {
              detail: {
                mensagem: "Há conflito a revisar",
                segredo_interno: "não pode vazar",
              },
            },
          },
        },
        "fallback",
      ),
    ).toBe("Há conflito a revisar");
  });

  it("não renderiza objeto arbitrário nem detalhe técnico", () => {
    expect(
      mensagemErroHttp(
        { response: { data: { detail: { erro: "objeto arbitrário" } } } },
        "fallback",
      ),
    ).toBe("fallback");
    expect(
      mensagemErroHttp(
        { response: { data: { detail: "provider timeout em http://localhost" } } },
        "fallback",
      ),
    ).toBe("fallback");
  });

  it("traduz validação Pydantic sem devolver objeto", () => {
    expect(
      mensagemErroHttp(
        {
          response: {
            status: 422,
            data: {
              detail: [{ loc: ["body", "titulo"], msg: "campo obrigatório" }],
            },
          },
        },
        "fallback",
      ),
    ).toBe("Verifique o campo titulo: campo obrigatório");
  });
});
