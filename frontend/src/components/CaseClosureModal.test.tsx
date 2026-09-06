import { describe, expect, it } from "vitest";
import {
  fechamentoPodeProsseguir,
  type DiagnosticoFechamento,
} from "./CaseClosureModal";

const base: DiagnosticoFechamento = {
  case_id: "case-1",
  pode_encerrar: true,
  requer_confirmacao_alertas: false,
  bloqueios: [],
  alertas: [],
  resumo: {
    prazos_ativos: 0,
    prazos_nao_confirmados: 0,
    tarefas_abertas: 0,
    financeiro_pendente: 0,
    pecas_nao_protocoladas: 0,
    proxima_acao_pendente: false,
  },
};

describe("fechamentoPodeProsseguir", () => {
  it("libera caso sem bloqueios nem alertas", () => {
    expect(fechamentoPodeProsseguir(base, false)).toBe(true);
  });

  it("nunca libera quando há bloqueio fatal", () => {
    const diagnostico: DiagnosticoFechamento = {
      ...base,
      pode_encerrar: false,
      bloqueios: [
        {
          codigo: "prazo_ativo",
          tipo: "prazo",
          id: "prazo-1",
          titulo: "Recurso",
          descricao: "Prazo pendente",
          destino: "/casos/case-1?tab=timeline",
        },
      ],
    };

    expect(fechamentoPodeProsseguir(diagnostico, false)).toBe(false);
    expect(fechamentoPodeProsseguir(diagnostico, true)).toBe(false);
  });

  it("exige confirmação explícita para alertas não fatais", () => {
    const diagnostico: DiagnosticoFechamento = {
      ...base,
      requer_confirmacao_alertas: true,
      alertas: [
        {
          codigo: "financeiro_pendente",
          tipo: "honorario",
          id: "fee-1",
          titulo: "Honorário pendente",
          descricao: "Honorário atrasado",
          destino: "/casos/case-1?tab=financeiro",
        },
      ],
    };

    expect(fechamentoPodeProsseguir(diagnostico, false)).toBe(false);
    expect(fechamentoPodeProsseguir(diagnostico, true)).toBe(true);
  });
});
