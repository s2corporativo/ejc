import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import Assinaturas from "./Assinaturas";

// GET /signatures/ responde envelope { data: [...] } (padrão do portal).
// A regressão auditada: setSolicitacoes(res.data) guardava o ENVELOPE no
// estado e `solicitacoes.map` explodia (ErrorBoundary em /assinaturas).
// asList() normaliza o envelope; estes testes cobrem os dois cenários.
const getMock = vi.fn();

vi.mock("../lib/api", () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: vi.fn(),
  },
  // Reexports usados pela store de auth (importada pela página).
  getAccessToken: () => null,
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

beforeEach(() => {
  getMock.mockReset();
});

describe("página /assinaturas", () => {
  it("renderiza lista vazia (EmptyState) com envelope { data: [] } sem quebrar", async () => {
    getMock.mockResolvedValue({ data: { data: [] } });
    render(<Assinaturas />);
    await waitFor(() => {
      expect(
        screen.getByText("Nenhuma solicitação de assinatura"),
      ).toBeTruthy();
    });
    expect(getMock).toHaveBeenCalledWith("/signatures/");
  });

  it("renderiza as solicitações vindas no envelope { data: [...] }", async () => {
    // Contrato real do backend (signatures.py): id UUID, título em
    // `documento`, status "pendente" e signatarios presente.
    getMock.mockResolvedValue({
      data: {
        data: [
          {
            id: "a4f6d0aa-0000-0000-0000-000000000001",
            document_id: "b4f6d0aa-0000-0000-0000-000000000002",
            documento: "Contrato de Honorários",
            status: "pendente",
            hash: "abc123def456ghi7…",
            signatarios: [
              { nome: "Fulano", email: "fulano@ejc.adv.br", papel: "parte" },
            ],
            created_at: "2026-07-10T12:00:00Z",
          },
        ],
      },
    });
    render(<Assinaturas />);
    await waitFor(() => {
      expect(screen.getByText("Contrato de Honorários")).toBeTruthy();
      expect(screen.getByText("Aguardando")).toBeTruthy();
      expect(screen.getByText("Fulano")).toBeTruthy();
    });
  });

  it("não quebra quando o item vem SEM `signatarios` e com status desconhecido", async () => {
    // Regressão do go-live: `sol.signatarios.some(...)` estourava TypeError
    // (ErrorBoundary em /assinaturas) porque a listagem do backend não
    // enviava `signatarios`; STATUS_CONFIG[status] também vinha undefined.
    getMock.mockResolvedValue({
      data: {
        data: [
          {
            id: "a4f6d0aa-0000-0000-0000-000000000003",
            documento: "Procuração Ad Judicia",
            status: "status_futuro_desconhecido",
            created_at: "2026-07-11T09:00:00Z",
          },
        ],
      },
    });
    render(<Assinaturas />);
    await waitFor(() => {
      expect(screen.getByText("Procuração Ad Judicia")).toBeTruthy();
    });
  });

  it("cai para lista vazia quando a API falha (sem tela branca)", async () => {
    getMock.mockRejectedValue(new Error("500"));
    render(<Assinaturas />);
    await waitFor(() => {
      expect(
        screen.getByText("Nenhuma solicitação de assinatura"),
      ).toBeTruthy();
    });
  });
});
