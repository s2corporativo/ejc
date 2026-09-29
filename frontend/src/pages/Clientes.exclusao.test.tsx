// @vitest-environment jsdom
// Exclusão de cliente (soft delete com trilha de auditoria). O backend exige
// admin/sócio (require_roles) e responde 409 { mensagem, bloqueios } quando
// há dependências (caso em representação ativa); ?forcar=true prossegue com
// decisão registrada. A UI espelha o gate e nunca força sem clique explícito.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";

const getMock = vi.fn();
const deleteMock = vi.fn();
const toastSuccess = vi.fn();
const toastError = vi.fn();
const estado = { role: "socio" };

vi.mock("../lib/api", () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: vi.fn().mockResolvedValue({ data: {} }),
    delete: (...a: unknown[]) => deleteMock(...a),
    patch: vi.fn().mockResolvedValue({ data: {} }),
  },
  getAccessToken: () => null,
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

vi.mock("../components/Toast", () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
    info: vi.fn(),
  },
}));

vi.mock("../stores/auth", () => ({
  useAuth: () => ({ user: { role: estado.role } }),
}));

vi.mock("../components/Dashboards", () => ({ ClientesStats: () => null }));
vi.mock("../components/Infosimples", () => ({ VerificarReceita: () => null }));

import Clientes from "./Clientes";

const CLIENTE = {
  id: "cli-1",
  tipo: "PF",
  nome: "Maria Souza",
  status: "ativo",
  created_at: "2026-09-01T00:00:00Z",
};

function montar() {
  return render(
    <MemoryRouter initialEntries={["/clientes"]}>
      <Routes>
        <Route path="/clientes" element={<Clientes />} />
        <Route path="/clientes/:id" element={<div>FICHA DESTINO</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  estado.role = "socio";
  getMock.mockReset();
  deleteMock.mockReset();
  toastSuccess.mockReset();
  toastError.mockReset();
  getMock.mockResolvedValue({
    data: { data: [CLIENTE], total: 1, page: 1, page_size: 20 },
  });
  deleteMock.mockResolvedValue({ data: {} });
});

afterEach(cleanup);

describe("Clientes — exclusão de cliente", () => {
  it("sócio exclui cliente e a listagem é recarregada", async () => {
    montar();
    await screen.findByText("Maria Souza");

    fireEvent.click(screen.getByTitle("Excluir cliente"));
    const titulo = await screen.findByText(/Excluir cliente/i);
    const modal = titulo.closest(".card")!;
    fireEvent.click(within(modal).getByText("Excluir"));

    await waitFor(() =>
      expect(deleteMock).toHaveBeenCalledWith("/clients/cli-1", undefined),
    );
    expect(deleteMock).not.toHaveBeenCalledWith("/clients/cli-1", {
      params: { forcar: true },
    });
    expect(deleteMock.mock.calls[0][1]).toBeUndefined();
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    // load() reexecutado após a exclusão
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(2));
  });

  it("409 mostra bloqueios e exige confirmação explícita para forçar", async () => {
    deleteMock.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          detail: {
            mensagem: "Exclusão bloqueada — resolva as pendências.",
            bloqueios: ["Caso 0001/2026 em representação ativa"],
          },
        },
      },
    });
    montar();
    await screen.findByText("Maria Souza");

    fireEvent.click(screen.getByTitle("Excluir cliente"));
    const titulo = await screen.findByText(/Excluir cliente/i);
    const modal = titulo.closest(".card")!;
    fireEvent.click(within(modal).getByText("Excluir"));

    await waitFor(() =>
      expect(
        screen.getByText(/Caso 0001\/2026 em representação ativa/),
      ).toBeTruthy(),
    );
    await waitFor(() => expect(toastError).toHaveBeenCalled());

    // Sem marcar "forçar", o botão permanece desabilitado
    expect(
      (within(modal).getByText("Excluir") as HTMLButtonElement).disabled,
    ).toBe(true);

    fireEvent.click(within(modal).getByText(/Confirmar mesmo assim/i));
    expect(
      (within(modal).getByText("Excluir") as HTMLButtonElement).disabled,
    ).toBe(false);
    fireEvent.click(within(modal).getByText("Excluir"));

    await waitFor(() =>
      expect(deleteMock).toHaveBeenCalledWith("/clients/cli-1", {
        params: { forcar: true },
      }),
    );
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
  });

  it("advogado e estagiário não veem a ação de excluir", async () => {
    estado.role = "advogado";
    montar();
    await screen.findByText("Maria Souza");
    expect(screen.queryByTitle("Excluir cliente")).toBeNull();

    estado.role = "estagiario";
    cleanup();
    montar();
    await screen.findByText("Maria Souza");
    expect(screen.queryByTitle("Excluir cliente")).toBeNull();
  });
});
