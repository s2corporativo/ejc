import { describe, expect, it } from "vitest";

import { montarPayloadCriacao, normalizarAnalise } from "./types";

describe("Entrada Única — reconciliação processual", () => {
  it("preserva vários CNJs sem escolher silenciosamente um deles", () => {
    const proposta = normalizarAnalise(
      {
        rascunho_id: "r1",
        reconciliacao_processual: [
          {
            numero_cnj: "1018284-13.2026.8.13.0027",
            status: "novo_processo",
            mensagem: "CNJ válido não localizado no EJC.",
          },
          {
            numero_cnj: "1015352-52.2026.8.13.0027",
            status: "novo_processo",
            mensagem: "CNJ válido não localizado no EJC.",
          },
          {
            numero_cnj: "0709938-44.2026.8.07.0018",
            status: "provavel_correspondencia",
            case_id: "case-64",
            numero_interno: "DPT-2026-0064",
            titulo: "Betim Baterias/TA Transportes x DER/DF",
            confianca: 0.92,
            mensagem: "Há forte correspondência com caso existente.",
          },
        ],
      },
      "u1",
    );

    expect(proposta).not.toBeNull();
    expect(proposta?.reconciliacoes).toHaveLength(3);
    expect(proposta?.numeroProcesso).toBe("");
    expect(proposta?.reconciliarCaseId).toBeNull();
  });

  it("pré-seleciona o único CNJ, mas não confirma correspondência provável", () => {
    const proposta = normalizarAnalise(
      {
        rascunho_id: "r2",
        reconciliacao_processual: [
          {
            numero_cnj: "0709938-44.2026.8.07.0018",
            status: "provavel_correspondencia",
            case_id: "case-64",
            numero_interno: "DPT-2026-0064",
            titulo: "Betim Baterias/TA Transportes x DER/DF",
            confianca: 0.92,
            mensagem: "Confirme antes de vincular.",
          },
        ],
      },
      "u1",
    );

    expect(proposta?.numeroProcesso).toBe("0709938-44.2026.8.07.0018");
    expect(proposta?.reconciliarCaseId).toBeNull();
    expect(proposta?.duplicateConfirmed).toBe(false);
  });

  it("envia CNJ e case_id somente depois da decisão explícita da tela", () => {
    const proposta = normalizarAnalise(
      {
        rascunho_id: "r3",
        reconciliacao_processual: [
          {
            numero_cnj: "0709938-44.2026.8.07.0018",
            status: "provavel_correspondencia",
            case_id: "case-64",
            numero_interno: "DPT-2026-0064",
            titulo: "Betim Baterias/TA Transportes x DER/DF",
            mensagem: "Confirme antes de vincular.",
          },
        ],
      },
      "u1",
    );
    expect(proposta).not.toBeNull();

    const payload = montarPayloadCriacao({
      ...proposta!,
      clienteNome: "Betim Baterias Automotivas Ltda.",
      area: "administrativo",
      titulo: "Betim Baterias x DER/DF",
      advogadoResponsavelId: "u1",
      reconciliarCaseId: "case-64",
      duplicateConfirmed: true,
      confirmoRevisao: true,
    });

    expect(payload.numero_processo).toBe("0709938-44.2026.8.07.0018");
    expect(payload.reconciliar_case_id).toBe("case-64");
    expect(payload.duplicate_confirmed).toBe(true);
    expect(payload.cliente).toBeUndefined();
    expect(payload.area).toBeUndefined();
    expect(payload.titulo).toBeUndefined();
    expect(payload.advogado_responsavel_id).toBeUndefined();
  });
});
