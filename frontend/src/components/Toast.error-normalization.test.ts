import { describe, expect, it } from "vitest";
import { normalizarMensagemToast, toast } from "./Toast";

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

  it("toast.error nunca despacha array/objeto cru para o React", () => {
    let recebido: unknown = null;
    const handler = (event: Event) => {
      recebido = (event as CustomEvent).detail;
    };
    window.addEventListener("ejc-toast", handler, { once: true });

    toast.error([
      {
        loc: ["body", "numero_processo"],
        msg: "Número CNJ inválido",
        input: "dado-que-nao-deve-ir-ao-toast",
      },
    ]);

    expect(recebido).toMatchObject({
      type: "error",
      message: "Número CNJ inválido",
    });
    expect(JSON.stringify(recebido)).not.toContain(
      "dado-que-nao-deve-ir-ao-toast",
    );
  });
});
