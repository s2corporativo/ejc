import { describe, expect, it } from "vitest";
import {
  MENSAGENS_DO_DIA,
  diaDoAno,
  mensagemDoDia,
} from "./mensagensDoDia";

describe("mensagensDoDia", () => {
  it("toda mensagem tem texto e referência conferível", () => {
    expect(MENSAGENS_DO_DIA.length).toBeGreaterThan(0);
    for (const mensagem of MENSAGENS_DO_DIA) {
      expect(mensagem.texto.trim().length).toBeGreaterThan(10);
      // Base auditável: versículo sem referência não entra na rotação.
      expect(mensagem.referencia).toMatch(/\d+:\d+/);
    }
  });

  it("diaDoAno calcula 1º de janeiro como dia 1 e 31 de dezembro como 365/366", () => {
    expect(diaDoAno(new Date(2026, 0, 1))).toBe(1);
    expect(diaDoAno(new Date(2026, 11, 31))).toBe(365);
    expect(diaDoAno(new Date(2024, 11, 31))).toBe(366); // bissexto
  });

  it("rotação é determinística: mesma data, mesma mensagem", () => {
    const data = new Date(2026, 7, 4);
    expect(mensagemDoDia(data)).toEqual(mensagemDoDia(new Date(2026, 7, 4)));
  });

  it("dias consecutivos rotacionam a mensagem", () => {
    const hoje = mensagemDoDia(new Date(2026, 7, 4));
    const amanha = mensagemDoDia(new Date(2026, 7, 5));
    expect(hoje).not.toEqual(amanha);
  });

  it("cobre o ano inteiro sem estourar o índice", () => {
    for (let dia = 0; dia < 366; dia++) {
      const data = new Date(2024, 0, 1 + dia);
      const mensagem = mensagemDoDia(data);
      expect(mensagem.texto).toBeTruthy();
    }
  });
});
