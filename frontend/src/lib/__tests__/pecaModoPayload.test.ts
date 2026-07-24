import { describe, expect, it } from "vitest";

import { montarPreparacaoModo } from "../pecaModoPayload";

const base = {
  caseId: "caso-1",
  tipoPeca: "contestacao",
  areaDireito: "civil",
};

describe("montarPreparacaoModo", () => {
  it("envia somente a instrução aplicável ao Modo Livre", () => {
    const payload = montarPreparacaoModo({
      ...base,
      modo: "livre",
      instrucaoLivre: "  Impugnar especificamente.  ",
      respostasGuiadas: { fatos_impugnados: "não deve ser enviado" },
    });

    expect(payload).toEqual({
      modo: "livre",
      case_id: "caso-1",
      tipo_peca: "contestacao",
      area_direito: "civil",
      instrucao_livre: "Impugnar especificamente.",
    });
  });

  it("envia somente as respostas do Modo Guiado", () => {
    const payload = montarPreparacaoModo({
      ...base,
      modo: "guiado",
      respostasGuiadas: {
        fatos_impugnados: "Cobrança já quitada.",
        pedidos: "Improcedência.",
      },
      instrucaoLivre: "não deve ser enviado",
    });

    expect(payload.respostas_guiadas).toEqual({
      fatos_impugnados: "Cobrança já quitada.",
      pedidos: "Improcedência.",
    });
    expect(payload).not.toHaveProperty("instrucao_livre");
  });

  it("mantém identidade, versão e hash no Modo Molde", () => {
    const payload = montarPreparacaoModo({
      ...base,
      modo: "molde",
      molde: {
        referencia: {
          documento_id: "doc-1",
          versao: 3,
          hash_conteudo: "abc123",
        },
        preservar: ["titulos", "estilo"],
        substituir: ["partes", "fatos", "pedidos_aplicaveis"],
      },
    });

    expect(payload.molde?.referencia).toEqual({
      documento_id: "doc-1",
      versao: 3,
      hash_conteudo: "abc123",
    });
    expect(payload).not.toHaveProperty("documentos_considerados");
  });

  it("envia documentos e aprovação somente no Modo Agente", () => {
    const payload = montarPreparacaoModo({
      ...base,
      modo: "agente",
      documentosConsiderados: [
        { documento_id: "doc-1", versao: 2, hash_conteudo: "hash-1" },
      ],
      aprovadoParaRedacao: true,
    });

    expect(payload.documentos_considerados).toEqual([
      { documento_id: "doc-1", versao: 2, hash_conteudo: "hash-1" },
    ]);
    expect(payload.aprovado_para_redacao).toBe(true);
    expect(payload).not.toHaveProperty("molde");
  });

  it("normaliza caso vazio para null", () => {
    const payload = montarPreparacaoModo({
      ...base,
      caseId: "   ",
      modo: "livre",
    });

    expect(payload.case_id).toBeNull();
    expect(payload.instrucao_livre).toBeNull();
  });
});
