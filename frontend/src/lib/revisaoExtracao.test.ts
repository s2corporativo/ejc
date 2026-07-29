import { describe, expect, it } from "vitest";
import {
  rascunhoCobreRevisao,
  urlRevisaoPendente,
  urlSemParamRevisao,
} from "./revisaoExtracao";
import type { IntakeRascunho } from "./intakeRascunho";

const rascunhoBase: IntakeRascunho = {
  form: { titulo: "Caso X" },
  extracao: { partes: { autor: "Fulano" } },
  caseId: "c1",
  uploadFeito: true,
  salvoEm: Date.now(),
};

describe("urlRevisaoPendente — FLX-048", () => {
  it("marca a revisão pendente na lista de casos", () => {
    expect(urlRevisaoPendente("c1")).toBe("/casos?revisao=c1");
  });

  it("escapa caseId com caracteres especiais", () => {
    expect(urlRevisaoPendente("a b")).toBe("/casos?revisao=a%20b");
  });
});

describe("rascunhoCobreRevisao — FLX-048", () => {
  it("cobre quando caseId bate e há extração", () => {
    expect(rascunhoCobreRevisao(rascunhoBase, "c1")).toBe(true);
  });

  it("não cobre sem rascunho persistido", () => {
    expect(rascunhoCobreRevisao(null, "c1")).toBe(false);
  });

  it("não cobre quando o caseId diverge", () => {
    expect(rascunhoCobreRevisao(rascunhoBase, "c2")).toBe(false);
  });

  it("não cobre sem extração materializável", () => {
    expect(
      rascunhoCobreRevisao({ ...rascunhoBase, extracao: null }, "c1"),
    ).toBe(false);
  });
});

describe("urlSemParamRevisao — FLX-048", () => {
  it("remove o param revisao deixando a URL limpa", () => {
    expect(urlSemParamRevisao("/casos", "?revisao=c1")).toBe("/casos");
  });

  it("preserva os demais params ao remover", () => {
    expect(urlSemParamRevisao("/casos", "?revisao=c1&arquivo=todos")).toBe(
      "/casos?arquivo=todos",
    );
  });

  it("é inócua quando não há o param", () => {
    expect(urlSemParamRevisao("/casos", "?arquivo=todos")).toBe(
      "/casos?arquivo=todos",
    );
  });
});
