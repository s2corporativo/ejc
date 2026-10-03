import { describe, expect, it } from "vitest";
import {
  apiDetailMessage,
  apiDetailNonemptyMessage,
  apiErrorMessage,
  caseCreationError,
  legacyDetailMessage,
} from "./apiError";
import { mensagemErroIA, MENSAGEM_IA_INDISPONIVEL } from "./iaErro";

const error = (detail: unknown, status = 400) => ({
  response: { status, data: { detail } },
});

describe("mensagens públicas de erro", () => {
  it("mantém as variantes históricas de mensagem vazia e fallback", () => {
    expect(apiDetailMessage(error(""), "Falha")).toBe("");
    expect(apiDetailNonemptyMessage(error(""), "Falha")).toBe("Falha");
    expect(apiDetailNonemptyMessage(error({ mensagem: "" }), "Falha")).toBe("");
    expect(legacyDetailMessage(error({ mensagem: "" }), "Falha")).toBe("");
    expect(
      legacyDetailMessage(error([{ msg: "Data inválida" }]), "Falha"),
    ).toBe('[{"msg":"Data inválida"}]');
  });
  it.each([
    ["Selecione um arquivo.", "Selecione um arquivo."],
    [{ mensagem: "Caso indisponível." }, "Caso indisponível."],
    [{ message: "Caso indisponível." }, "Caso indisponível."],
    [
      [
        "Data inválida.",
        { msg: "Valor inválido.", input: "CONTEÚDO SINTÉTICO" },
      ],
      "Data inválida.; Valor inválido.",
    ],
  ])("preserva a orientação do servidor para %j", (detail, expected) => {
    expect(apiDetailMessage(error(detail), "Tente novamente.")).toBe(expected);
  });

  it("não serializa payload desconhecido, nem valores de entrada no erro", () => {
    expect(
      apiDetailMessage(
        error({ input: "CONTEÚDO SINTÉTICO" }),
        "Tente novamente.",
      ),
    ).toBe("Tente novamente.");
    expect(
      caseCreationError(
        error(
          [
            {
              loc: ["body", "data_fato"],
              msg: "Formato inválido",
              input: "CONTEÚDO SINTÉTICO",
            },
          ],
          422,
        ),
        "Erro ao salvar",
      ),
    ).toBe("data fato: Formato inválido");
  });

  it("preserva o fallback de criação e de falha sem resposta HTTP", () => {
    expect(
      caseCreationError(error(undefined, 422), "Erro ao salvar"),
    ).toContain("Revise os campos destacados");
    expect(caseCreationError(undefined, "Erro ao salvar")).toBe(
      "Erro ao salvar",
    );
    expect(
      apiErrorMessage(new Error("Conexão interrompida"), "Tente novamente."),
    ).toBe("Conexão interrompida");
  });

  it("continua ocultando infraestrutura nas superfícies de IA", () => {
    expect(
      mensagemErroIA(error({ message: "Ollama timeout em localhost" })),
    ).toBe(MENSAGEM_IA_INDISPONIVEL);
  });
});
