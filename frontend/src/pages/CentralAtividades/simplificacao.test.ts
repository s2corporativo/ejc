import { describe, expect, it } from "vitest";

import {
  correspondeBusca,
  detectarConflitosAgendaLegada,
  pertenceCaixaEntrada,
  precisaConferencia,
  situacaoOperacional,
} from "./simplificacao";

describe("simplificação operacional da Central de Atividades", () => {
  it("normaliza os estados heterogêneos sem perder cancelado", () => {
    expect(situacaoOperacional("a_fazer")).toBe("pendente");
    expect(situacaoOperacional("fazendo")).toBe("andamento");
    expect(situacaoOperacional("tratada")).toBe("concluido");
    expect(situacaoOperacional("cancelado")).toBe("cancelado");
  });

  it("leva prazo crítico sem segunda conferência para a caixa de entrada", () => {
    const prazo = {
      id: "p1",
      fonte: "prazo" as const,
      titulo: "Contestação",
      status: "pendente",
      prioridade: "critica",
      confirmado: true,
      conferido_por: null,
    };
    expect(precisaConferencia(prazo)).toBe(true);
    expect(pertenceCaixaEntrada(prazo)).toBe(true);
  });

  it("não pede conferência para prazo crítico já concluído", () => {
    expect(
      precisaConferencia({
        fonte: "prazo",
        status: "concluido",
        prioridade: "critica",
        confirmado: true,
        conferido_por: null,
      }),
    ).toBe(false);
  });

  it("detecta somente colisões legadas do mesmo responsável/data/hora", () => {
    const conflitos = detectarConflitosAgendaLegada([
      { id: "1", data_evento: "2026-09-02", hora: "09:00", responsavel_id: "u1" },
      { id: "2", data_evento: "2026-09-02", hora: " 09:00 ", responsavel_id: "u1" },
      { id: "3", data_evento: "2026-09-02", hora: "09:00", responsavel_id: "u2" },
      { id: "4", data_evento: "2026-09-02", hora: null, responsavel_id: "u1" },
    ]);
    expect(conflitos).toHaveLength(1);
    expect(conflitos[0].ids).toEqual(["1", "2"]);
  });

  it("pesquisa por título, caso e responsável", () => {
    const item = {
      id: "x",
      fonte: "tarefa" as const,
      titulo: "Protocolar defesa",
      descricao: "Revisar anexos",
      caso_titulo: "Cliente Alfa",
    };
    expect(correspondeBusca(item, "defesa")).toBe(true);
    expect(correspondeBusca(item, "alfa")).toBe(true);
    expect(correspondeBusca(item, "joão", "João Pedro")).toBe(true);
    expect(correspondeBusca(item, "inexistente", "João Pedro")).toBe(false);
  });
});
