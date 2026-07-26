import { describe, expect, it } from "vitest";
import {
  MENSAGEM_FERRAMENTA_NAO_HOMOLOGADA,
  MENSAGEM_IA_INDISPONIVEL,
  mensagemErroFerramenta,
  mensagemErroIA,
} from "./iaErro";

function erroCom(detail: unknown, status?: number) {
  return { response: { status, data: { detail } } };
}

describe("mensagemErroFerramenta", () => {
  it("traduz 503 ferramenta_nao_homologada para mensagem controlada", () => {
    const err = erroCom(
      { codigo: "ferramenta_nao_homologada", mensagem: "qualquer" },
      503,
    );
    expect(mensagemErroFerramenta(err)).toBe(
      MENSAGEM_FERRAMENTA_NAO_HOMOLOGADA,
    );
  });

  it("nunca devolve objeto cru: extrai detail.mensagem ou usa fallback", () => {
    expect(
      mensagemErroFerramenta(erroCom({ mensagem: "Data inválida." }, 400)),
    ).toBe("Data inválida.");
    expect(typeof mensagemErroFerramenta(erroCom({ foo: "bar" }, 500))).toBe(
      "string",
    );
    expect(mensagemErroFerramenta(undefined)).toBe("Falha no cálculo");
  });

  it("deixa passar detail string do backend", () => {
    expect(mensagemErroFerramenta(erroCom("Informe a data.", 422))).toBe(
      "Informe a data.",
    );
  });

  it("traduz o array de validação do Pydantic apontando o campo", () => {
    const err = erroCom(
      [{ loc: ["query", "data_marco"], msg: "Field required" }],
      422,
    );
    expect(mensagemErroFerramenta(err)).toBe(
      "Verifique o campo data marco: Field required",
    );
  });

  it("cai no genérico quando o array de validação não tem campo legível", () => {
    const generica = "Verifique os dados informados e tente novamente.";
    expect(mensagemErroFerramenta(erroCom([{ loc: ["query"] }], 422))).toBe(
      generica,
    );
    expect(mensagemErroFerramenta(erroCom(["texto solto"], 422))).toBe(
      generica,
    );
  });
});

describe("mensagemErroIA", () => {
  it("devolve o texto padrão quando não há detail", () => {
    expect(mensagemErroIA(undefined)).toBe(MENSAGEM_IA_INDISPONIVEL);
    expect(mensagemErroIA(new Error("boom"))).toBe(MENSAGEM_IA_INDISPONIVEL);
  });

  it("bloqueia mensagens com dialeto de infraestrutura", () => {
    const tecnicas = [
      "Falha na IA. A IA pode estar desabilitada (.env).",
      "GROQ_API_KEY não configurada para transcrição",
      "Todos os provedores falharam para task=estrategia",
      "Ollama indisponível: [Errno -2] Name or service not known",
      "configure Ollama",
      "Erro do provider openai: timeout",
    ];
    for (const detail of tecnicas) {
      expect(mensagemErroIA(erroCom(detail))).toBe(MENSAGEM_IA_INDISPONIVEL);
    }
  });

  it("deixa passar detail leigo do backend", () => {
    const leiga = "Descreva os fatos com pelo menos 30 caracteres.";
    expect(mensagemErroIA(erroCom(leiga))).toBe(leiga);
  });

  it("aceita detail objeto {mensagem} e usa fallback custom", () => {
    expect(mensagemErroIA(erroCom({ mensagem: "Caso sem descrição." }))).toBe(
      "Caso sem descrição.",
    );
    expect(mensagemErroIA(erroCom(null), "Falha X")).toBe("Falha X");
  });
});
