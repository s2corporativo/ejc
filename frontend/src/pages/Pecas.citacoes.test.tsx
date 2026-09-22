// @vitest-environment jsdom
// P2-9 (auditoria de IA 2026-08-18): o gate antialucinação devolve 409 quando a
// peça cita o que a base oficial não confirma. Antes, o advogado via a mensagem
// de erro e o fluxo MORRIA ali — não havia como corrigir nem como assumir a
// responsabilidade por escrito, e o único caminho de aprovação da peça ficava
// fechado. Estes testes fixam o contrato: o 409 vira decisão dentro do dialog,
// e o override só sai com justificativa (que o backend audita).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";

vi.mock("../components/PecaGeneratorModal", () => ({ default: () => null }));
vi.mock("../components/CaseFilterChip", () => ({ default: () => null }));
vi.mock("../components/ContextualAIAssistant", () => ({ default: () => null }));

import api from "../lib/api";
import Pecas from "./Pecas";

vi.mock("../lib/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  getAccessToken: () => null,
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

const PECA = {
  id: "doc-1",
  titulo: "ContestacaoDeTeste",
  tipo_peca: "contestacao",
  status: "rascunho",
  ai_generated: true,
  human_reviewed: false,
  created_at: "2026-08-18T12:00:00Z",
};

const BLOQUEIO_409 = {
  response: {
    status: 409,
    data: {
      detail: {
        erro: "citacoes_nao_verificadas",
        mensagem: "Output de IA contém citações bloqueantes.",
        politica: "bloquear",
        score: 42,
        motivos: ["2 citações suspeitas"],
        bloqueantes: [
          { rotulo: "Súmula 999 STJ", aviso: "fora da faixa plausível" },
        ],
      },
    },
  },
};

beforeEach(() => {
  vi.mocked(api.get).mockResolvedValue({
    data: { data: [PECA], total: 1, page: 1, page_size: 50 },
  });
  vi.mocked(api.post).mockReset();
});

afterEach(cleanup);

async function abrirDialogDeAprovacao() {
  render(
    <MemoryRouter>
      <Pecas />
    </MemoryRouter>,
  );
  // A lista renderiza em cartão (mobile) e em tabela (desktop) — em jsdom os
  // dois estão no DOM; qualquer um abre o mesmo dialog.
  // PR #1425 renomeou a ação da fila de "Revisar e Aprovar" para "Revisar peça".
  // O gate de citações que este arquivo cobre não mudou — só o rótulo do botão.
  const [botao] = await screen.findAllByText(/Revisar peça/i);
  fireEvent.click(botao);
  const observacoes = await screen.findByPlaceholderText(
    /Observações da revisão/i,
  );
  fireEvent.change(observacoes, {
    target: { value: "Conferi os fatos e a fundamentação." },
  });
  // Idem: "Aprovar peça" virou "Aprovar e assinar" (conferência e assinatura
  // num ato só, PR #622/#1425). O comportamento aferido aqui é o mesmo.
  return screen.getByRole("button", { name: /Aprovar e assinar/i });
}

describe("Peças — gate de citações na aprovação", () => {
  it("mostra as citações bloqueantes do 409 em vez de encerrar o fluxo", async () => {
    vi.mocked(api.post).mockRejectedValueOnce(BLOQUEIO_409);
    const aprovar = await abrirDialogDeAprovacao();
    fireEvent.click(aprovar);

    await waitFor(() =>
      expect(screen.getByText(/Citações não confirmadas/i)).toBeTruthy(),
    );
    expect(screen.getByText(/Súmula 999 STJ/)).toBeTruthy();
    // O caminho de saída aparece: justificar e assumir.
    expect(
      screen.getByPlaceholderText(/Justificativa para eventual override/i),
    ).toBeTruthy();
  });

  it("não envia override sem justificativa escrita", async () => {
    vi.mocked(api.post).mockRejectedValueOnce(BLOQUEIO_409);
    const aprovar = await abrirDialogDeAprovacao();
    fireEvent.click(aprovar);
    await screen.findByPlaceholderText(/Justificativa para eventual override/i);

    // O fluxo não tem mais um botão separado de override: o MESMO "Aprovar e
    // assinar" é reusado, e só manda o override quando há justificativa.
    const chamadasAntes = vi.mocked(api.post).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: /Aprovar e assinar/i }));
    await waitFor(() =>
      expect(
        screen.getByText(/registre uma justificativa por escrito/i),
      ).toBeTruthy(),
    );
    expect(vi.mocked(api.post).mock.calls.length).toBe(chamadasAntes);
  });

  it("envia override com a justificativa quando o advogado assume", async () => {
    vi.mocked(api.post)
      .mockRejectedValueOnce(BLOQUEIO_409)
      .mockResolvedValueOnce({ data: {} });
    const aprovar = await abrirDialogDeAprovacao();
    fireEvent.click(aprovar);
    const justificativa = await screen.findByPlaceholderText(
      /Justificativa para eventual override/i,
    );
    fireEvent.change(justificativa, {
      target: { value: "Conferi a súmula no site do STJ; está correta." },
    });
    // Mesmo botão do fluxo normal: com justificativa preenchida, ele reenvia
    // a aprovação já com o override.
    fireEvent.click(screen.getByRole("button", { name: /Aprovar e assinar/i }));

    await waitFor(() => expect(vi.mocked(api.post).mock.calls.length).toBe(2));
    const [rota, corpo] = vi.mocked(api.post).mock.calls[1];
    expect(rota).toBe("/legal-docs/doc-1/conferir-e-assinar");
    expect(corpo).toMatchObject({
      override_citacoes: true,
      justificativa_override: "Conferi a súmula no site do STJ; está correta.",
    });
  });

  it("aprovação normal não manda override nenhum", async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: {} });
    const aprovar = await abrirDialogDeAprovacao();
    fireEvent.click(aprovar);

    await waitFor(() => expect(vi.mocked(api.post)).toHaveBeenCalled());
    const [, corpo] = vi.mocked(api.post).mock.calls[0];
    expect(corpo).not.toHaveProperty("override_citacoes");
  });
});
