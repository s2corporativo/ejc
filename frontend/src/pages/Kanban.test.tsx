// @vitest-environment jsdom
// Achado do security-auditor (docs/PLANO_FUSAO_CASO_UNICO.md §4.3-5): mover
// um cartão para uma coluna de arquivamento/encerramento sincronizava o
// status do caso sem o gate de papel nem o pós-mortem exigidos pelos
// endpoints dedicados. O backend passou a recusar (422); este teste cobre
// que a UI explica a recusa em vez de reverter o cartão em silêncio.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import Kanban from "./Kanban";

const getMock = vi.fn();
const patchMock = vi.fn();
const toastError = vi.fn();

vi.mock("../lib/api", () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    patch: (...a: unknown[]) => patchMock(...a),
  },
}));

vi.mock("../components/Toast", () => ({
  toast: { success: vi.fn(), error: (...a: unknown[]) => toastError(...a) },
}));

const COLUNAS = [
  { id: "c1", name: "Em andamento", legal_area: "default", position: 0 },
  { id: "c2", name: "Em elaboração", legal_area: "default", position: 1 },
  { id: "c3", name: "Arquivado", legal_area: "default", position: 2 },
];

const CASO = {
  id: "caso-1",
  titulo: "Ação de cobrança",
  numero_interno: "DPT-2026-0001",
  kanban_column: "Em andamento",
  case_type: "judicial",
};

function renderizar() {
  return render(
    <MemoryRouter>
      <Kanban />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  getMock.mockReset();
  patchMock.mockReset();
  toastError.mockReset();
  getMock.mockImplementation((url: string) => {
    if (url.startsWith("/kanban-columns"))
      return Promise.resolve({ data: COLUNAS });
    if (url.startsWith("/cases/"))
      return Promise.resolve({ data: { data: [CASO] } });
    return Promise.resolve({ data: {} });
  });
});

describe("Kanban — recusa de arquivar/encerrar via arrasto", () => {
  it("exibe o motivo da recusa quando o backend rejeita a coluna terminal", async () => {
    patchMock.mockRejectedValue({
      response: { data: { detail: "Use POST /cases/{id}/arquivar" } },
    });
    renderizar();

    await waitFor(() => {
      expect(screen.getByText("Ação de cobrança")).toBeTruthy();
    });

    const select = screen.getByDisplayValue(
      "Em andamento",
    ) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "Arquivado" } });

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith("Use POST /cases/{id}/arquivar");
    });
    // Recarrega a lista para o cartão voltar à coluna real (o card já havia
    // sido movido otimisticamente antes da resposta do servidor).
    expect(
      getMock.mock.calls.filter(([u]) => String(u).startsWith("/cases/"))
        .length,
    ).toBeGreaterThan(1);
  });

  it("move o cartão normalmente para coluna não terminal", async () => {
    patchMock.mockResolvedValue({
      data: { ok: true, status_sincronizado: null },
    });
    renderizar();

    await waitFor(() => {
      expect(screen.getByText("Ação de cobrança")).toBeTruthy();
    });

    const select = screen.getByDisplayValue(
      "Em andamento",
    ) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "Em elaboração" } });

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith(
        "/cases/caso-1/kanban",
        expect.objectContaining({ kanban_column: "Em elaboração" }),
      );
    });
    expect(toastError).not.toHaveBeenCalled();
  });
});
