import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AnaliseCasoIA from "./AnaliseCasoIA";

// A página conversa com o backend só por api (axios) e streamSSE (SSE). Ambos
// são mockados: os testes cobrem o esqueleto de UI (lista de sessões, estado
// vazio, abertura de uma conversa) sem tocar rede nem stream real.
const getMock = vi.fn();
const postMock = vi.fn();
const patchMock = vi.fn();
const deleteMock = vi.fn();

vi.mock("../lib/api", () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    patch: (...args: unknown[]) => patchMock(...args),
    delete: (...args: unknown[]) => deleteMock(...args),
  },
  // Reexports consumidos pela cadeia de imports (store de auth etc.).
  getAccessToken: () => null,
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

vi.mock("../lib/stream", () => ({
  streamSSE: vi.fn(),
  SSEHttpError: class SSEHttpError extends Error {
    status = 0;
  },
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <AnaliseCasoIA />
    </MemoryRouter>,
  );
}

const SESSAO = {
  id: "s1",
  case_id: null,
  titulo: "Rescisão indireta — Cliente X",
  nivel: "alto",
  area: null,
  arquivada: false,
  created_at: "2026-07-20T10:00:00Z",
  updated_at: "2026-07-20T10:05:00Z",
  total_mensagens: 2,
  ultima_mensagem_preview: "Resumo preliminar do caso.",
  ultima_atividade: "2026-07-20T10:05:00Z",
};

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  patchMock.mockReset();
  deleteMock.mockReset();
});

describe("página /analise-caso-ia", () => {
  it("mostra o estado vazio quando não há análises", async () => {
    getMock.mockImplementation((url: string) => {
      if (url.startsWith("/analise-caso-ia/sessoes"))
        return Promise.resolve({ data: [] });
      return Promise.resolve({ data: { data: [] } }); // GET /cases/
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Nenhuma análise ainda")).toBeTruthy();
    });
    // O aviso de compliance (rascunho/revisão humana) está sempre visível.
    expect(screen.getAllByText(/Nova análise/i).length).toBeGreaterThan(0);
  });

  it("lista as sessões retornadas pelo backend", async () => {
    getMock.mockImplementation((url: string) => {
      if (url.startsWith("/analise-caso-ia/sessoes"))
        return Promise.resolve({ data: [SESSAO] });
      return Promise.resolve({ data: { data: [] } });
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Rescisão indireta — Cliente X")).toBeTruthy();
    });
    expect(screen.getByText("Resumo preliminar do caso.")).toBeTruthy();
  });

  it("abre a conversa e renderiza as bolhas ao clicar na sessão", async () => {
    const detalhe = {
      ...SESSAO,
      mensagens: [
        {
          id: "m1",
          sessao_id: "s1",
          papel: "user",
          conteudo: "Qual o risco desta causa?",
          anexo_nome: null,
          ai_log_id: null,
          is_rascunho: false,
          created_at: "2026-07-20T10:00:00Z",
        },
        {
          id: "m2",
          sessao_id: "s1",
          papel: "assistant",
          conteudo: "Analise preliminar do risco processual.",
          anexo_nome: null,
          ai_log_id: "log1",
          is_rascunho: true,
          created_at: "2026-07-20T10:01:00Z",
        },
      ],
    };
    getMock.mockImplementation((url: string) => {
      if (url === "/analise-caso-ia/sessoes/s1")
        return Promise.resolve({ data: detalhe });
      if (url.startsWith("/analise-caso-ia/sessoes"))
        return Promise.resolve({ data: [SESSAO] });
      return Promise.resolve({ data: { data: [] } });
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Rescisão indireta — Cliente X")).toBeTruthy(),
    );
    fireEvent.click(screen.getByText("Rescisão indireta — Cliente X"));

    await waitFor(() => {
      expect(screen.getByText("Qual o risco desta causa?")).toBeTruthy();
      expect(
        screen.getByText("Analise preliminar do risco processual."),
      ).toBeTruthy();
    });
  });
});
