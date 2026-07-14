// @vitest-environment jsdom
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
        solicitacao_atrasada: false,
        solicitacao_prazo: "2026-07-15T18:00:00Z",
        solicitacao_prioridade: "alta",
        solicitacao_responsavel_id: "user-1",
        task_id: "task-1",
        contato_status: "confirmado",
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
    get.mockImplementation((url: string) => {
      if (url === "/atendimentos/responsaveis") {
        return Promise.resolve({
          data: [{ id: "user-1", nome: "Dra. Responsável", role: "advogado" }],
        });
      }
      if (url.endsWith("/historico")) {
        return Promise.resolve({ data: [] });
      }
      return Promise.resolve(response);
    });
    post.mockResolvedValue({ data: { id: "novo-atendimento" } });
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

  it("cria tarefa com prioridade e responsável a partir da solicitação", async () => {
    renderTimeline();

    fireEvent.click(
      await screen.findByRole("button", { name: "Novo atendimento" }),
    );
    fireEvent.change(
      screen.getByLabelText("Recado / registro do atendimento"),
      {
        target: {
          value: "Cliente solicitou análise e retorno sobre o documento.",
        },
      },
    );
    fireEvent.change(screen.getByLabelText("O que foi solicitado"), {
      target: { value: "Revisar o documento enviado pelo cliente." },
    });
    fireEvent.change(screen.getByLabelText("Prioridade"), {
      target: { value: "urgente" },
    });
    fireEvent.change(screen.getByLabelText("Responsável pela solicitação"), {
      target: { value: "user-1" },
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Registrar atendimento" }),
    );

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        "/atendimentos",
        expect.objectContaining({
          solicitacao: "Revisar o documento enviado pelo cliente.",
          solicitacao_prioridade: "urgente",
          solicitacao_responsavel_id: "user-1",
          criar_tarefa: true,
          contato_status: "confirmado",
        }),
      );
    });
  });

  it("exige confirmação humana após uma ação de contato rápido", async () => {
    const initiatedResponse = {
      ...response,
      data: {
        ...response.data,
        items: [
          {
            ...response.data.items[0],
            contato_status: "iniciado",
          },
        ],
      },
    };
    get.mockImplementation((url: string) => {
      if (url === "/atendimentos/responsaveis") {
        return Promise.resolve({ data: [] });
      }
      return Promise.resolve(initiatedResponse);
    });

    renderTimeline();

    fireEvent.click(
      await screen.findByRole("button", { name: "Confirmar contato" }),
    );

    await waitFor(() => {
      expect(patch).toHaveBeenCalledWith("/atendimentos/atendimento-1", {
        contato_status: "confirmado",
      });
    });
  });
});
