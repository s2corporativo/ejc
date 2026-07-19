import { describe, expect, it } from "vitest";
import { MENSAGEM_IA_INDISPONIVEL, mensagemErroIA } from "./iaErro";

function erroCom(detail: unknown) {
  return { response: { data: { detail } } };
}

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
