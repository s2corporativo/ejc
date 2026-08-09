import { describe, expect, it } from "vitest";
import { normalizarMensagemToast } from "./Toast";

describe("normalizarMensagemToast", () => {
  it("preserva mensagens string", () => {
    expect(normalizarMensagemToast("Número CNJ inválido")).toBe(
      "Número CNJ inválido",
    );
  });

  it("extrai msg de detail Pydantic sem serializar input", () => {
    const detail = [
      {
        type: "value_error",
        loc: ["body", "numero_processo"],
        msg: "Número CNJ inválido",
        input: "12345678901234567890",
      },
    ];

    const mensagem = normalizarMensagemToast(detail);
    expect(mensagem).toBe("Número CNJ inválido");
    expect(mensagem).not.toContain("12345678901234567890");
  });

  it("combina no máximo três mensagens estruturadas", () => {
    const detail = [
      { msg: "Erro 1" },
      { msg: "Erro 2" },
      { msg: "Erro 3" },
      { msg: "Erro 4" },
    ];

    expect(normalizarMensagemToast(detail)).toBe(
      "Erro 1 · Erro 2 · Erro 3 · +1 validação(ões)",
    );
  });

  it("aceita detail aninhado e objetos com message", () => {
    expect(
      normalizarMensagemToast({ detail: [{ message: "Campo inválido" }] }),
    ).toBe("Campo inválido");
  });

  it("usa fallback seguro para objeto sem mensagem", () => {
    expect(normalizarMensagemToast({ input: "não exibir" })).toBe(
      "Ocorreu um erro. Tente novamente.",
    );
  });
});
