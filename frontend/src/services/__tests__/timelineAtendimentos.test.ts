import { beforeEach, describe, expect, it, vi } from "vitest";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("../../lib/api", () => ({
  default: { get },
}));

import {
  carregarAtendimentosCaso,
  normalizarAtendimentosCaso,
} from "../timelineAtendimentos";

describe("timelineAtendimentos", () => {
  beforeEach(() => get.mockReset());

  it("normaliza somente atendimentos do caso esperado", () => {
    const resultado = normalizarAtendimentosCaso(
      {
        items: [
          {
            id: "a-1",
            case_id: "case-1",
            tipo: "whatsapp",
            data_atendimento: "2026-07-24T10:00:00-03:00",
            resumo: "Cliente encaminhou o comprovante.",
            solicitacao: "Confirmar a juntada.",
            solicitacao_atendida: false,
            solicitacao_atrasada: true,
            proximo_passo: "Protocolar manifestação.",
            contato_status: "confirmado",
          },
          {
            id: "a-2",
            case_id: "case-2",
            tipo: "email",
            data_atendimento: "2026-07-24T11:00:00-03:00",
            resumo: "Conteúdo de outro processo.",
            solicitacao_atendida: false,
          },
        ],
      },
      "case-1",
    );

    expect(resultado.eventos).toHaveLength(1);
    expect(resultado.eventos[0]).toEqual({
      data: "2026-07-24T10:00:00-03:00",
      categoria: "atendimento",
      tipo: "whatsapp",
      descricao:
        "Cliente encaminhou o comprovante. · Solicitação atrasada: Confirmar a juntada. · Próximo passo: Protocolar manifestação.",
    });
    expect(resultado.resumo).toEqual({
      total: 1,
      pendentes: 0,
      atrasados: 1,
      atendidos: 0,
    });
  });

  it("descarta data inválida e resumo vazio", () => {
    const resultado = normalizarAtendimentosCaso(
      {
        items: [
          {
            id: "a-1",
            case_id: "case-1",
            tipo: "ligacao",
            data_atendimento: "data-inválida",
            resumo: "Resumo válido.",
            solicitacao_atendida: false,
          },
          {
            id: "a-2",
            case_id: "case-1",
            tipo: "email",
            data_atendimento: "2026-07-24T10:00:00-03:00",
            resumo: "   ",
            solicitacao_atendida: false,
          },
        ],
      },
      "case-1",
    );

    expect(resultado.eventos).toEqual([]);
    expect(resultado.resumo.total).toBe(0);
  });

  it("recalcula o resumo a partir do escopo filtrado", () => {
    const resultado = normalizarAtendimentosCaso(
      {
        items: [
          {
            id: "p",
            case_id: "case-1",
            tipo: "email",
            data_atendimento: "2026-07-20T10:00:00Z",
            resumo: "Pedido pendente.",
            solicitacao: "Enviar documento.",
            solicitacao_atendida: false,
          },
          {
            id: "c",
            case_id: "case-1",
            tipo: "protocolo",
            data_atendimento: "2026-07-22T10:00:00Z",
            resumo: "Pedido concluído.",
            solicitacao: "Protocolar petição.",
            solicitacao_atendida: true,
          },
          {
            id: "outro",
            case_id: "case-2",
            tipo: "whatsapp",
            data_atendimento: "2026-07-23T10:00:00Z",
            resumo: "Não pode entrar.",
            solicitacao: "Solicitação alheia.",
            solicitacao_atendida: false,
            solicitacao_atrasada: true,
          },
        ],
      },
      "case-1",
    );

    expect(resultado.eventos.map((evento) => evento.tipo)).toEqual([
      "protocolo",
      "email",
    ]);
    expect(resultado.resumo).toEqual({
      total: 2,
      pendentes: 1,
      atrasados: 0,
      atendidos: 1,
    });
  });

  it("não transporta campos privados ou identificadores pessoais", () => {
    const resultado = normalizarAtendimentosCaso(
      {
        items: [
          {
            id: "a-1",
            case_id: "case-1",
            tipo: "reuniao_virtual",
            data_atendimento: "2026-07-24T10:00:00Z",
            resumo: "Reunião de alinhamento.",
            solicitacao_atendida: false,
            observacoes_privadas: "estratégia interna",
            client_id: "cliente-secreto",
            advogado_responsavel_id: "user-secreto",
          } as never,
        ],
      },
      "case-1",
    );

    const serializado = JSON.stringify(resultado);
    expect(serializado).not.toContain("estratégia interna");
    expect(serializado).not.toContain("cliente-secreto");
    expect(serializado).not.toContain("user-secreto");
  });

  it("consulta somente pelo caso e com paginação limitada", async () => {
    get.mockResolvedValue({ data: { items: [] } });

    await carregarAtendimentosCaso(" case-1 ");

    expect(get).toHaveBeenCalledWith("/atendimentos", {
      params: { case_id: "case-1", page: 1, per_page: 100 },
    });
  });

  it("não consulta o backend quando o caso está vazio", async () => {
    const resultado = await carregarAtendimentosCaso("   ");

    expect(get).not.toHaveBeenCalled();
    expect(resultado.eventos).toEqual([]);
  });
});
