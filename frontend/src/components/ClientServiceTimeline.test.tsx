import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { get, post, patch } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  default: { get, post, patch },
}));

vi.mock("./Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import ClientServiceTimeline from "./ClientServiceTimeline";

const response = {
  data: {
    total: 1,
    page: 1,
    per_page: 100,
    items: [
      {
        id: "atendimento-1",
        client_id: "cliente-1",
        case_id: "caso-1",
        tipo: "whatsapp",
        data_atendimento: "2026-07-13T14:30:00",
        resumo: "Cliente pediu retorno sobre a movimentação processual.",
        solicitacao: "Enviar a cópia da última decisão.",
        solicitacao_atendida: false,
        atendida_em: null,
        proximo_passo: null,
        pode_editar: true,
      },
    ],
  },
};

function renderTimeline() {
  return render(
    <MemoryRouter>
      <ClientServiceTimeline
        clientId="cliente-1"
        cases={[
          {
            id: "caso-1",
            numero_interno: "EJC-2026-001",
            titulo: "Ação de cobrança",
          },
        ]}
      />
    </MemoryRouter>,
  );
}

describe("ClientServiceTimeline", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    patch.mockReset();
    get.mockResolvedValue(response);
    patch.mockResolvedValue({ data: { ok: true } });
  });

  it("mostra recado, solicitação, dia/hora e situação", async () => {
    renderTimeline();

    expect(
      await screen.findByText(
        "Cliente pediu retorno sobre a movimentação processual.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Enviar a cópia da última decisão.")).toBeTruthy();
    expect(screen.getByText("Solicitação pendente")).toBeTruthy();
    expect(screen.getByText(/14:30/)).toBeTruthy();
    expect(get).toHaveBeenCalledWith("/atendimentos", {
      params: { client_id: "cliente-1", page: 1, per_page: 100 },
    });
  });

  it("permite marcar uma solicitação como atendida", async () => {
    renderTimeline();

    const button = await screen.findByRole("button", {
      name: "Marcar como atendida",
    });
    fireEvent.click(button);

    await waitFor(() => {
      expect(patch).toHaveBeenCalledWith("/atendimentos/atendimento-1", {
        solicitacao_atendida: true,
      });
    });
  });
});
