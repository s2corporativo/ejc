// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../lib/api";
import { toast } from "../components/Toast";
import Lixeira from "./Lixeira";

vi.mock("../lib/api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock("../components/Toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

const getMock = vi.mocked(api.get);
const postMock = vi.mocked(api.post);
const erroToast = vi.mocked(toast.error);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Lixeira — paginação e restauração", () => {
  it("navega para registros além da primeira página", async () => {
    getMock
      .mockResolvedValueOnce({
        data: {
          data: [
            {
              id: "c1",
              rotulo: "Cliente da primeira página",
              excluido_em: "2026-08-01T12:00:00Z",
            },
          ],
          total: 31,
          page: 1,
          page_size: 30,
        },
      } as any)
      .mockResolvedValueOnce({
        data: {
          data: [
            {
              id: "c31",
              rotulo: "Cliente da segunda página",
              excluido_em: "2026-08-02T12:00:00Z",
            },
          ],
          total: 31,
          page: 2,
          page_size: 30,
        },
      } as any);

    render(<Lixeira />);

    await screen.findByText("Cliente da primeira página");
    expect(screen.getByText(/página 1 de 2/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /próxima/i }));

    await screen.findByText("Cliente da segunda página");
    expect(screen.getByText(/página 2 de 2/i)).toBeTruthy();
    expect(getMock).toHaveBeenLastCalledWith("/trash/", {
      params: { entidade: "clients", page: 2, page_size: 30 },
    });
  });

  it("exibe ao operador a orientação do backend quando pai ainda está na lixeira", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        data: [
          {
            id: "case-1",
            rotulo: "Caso dependente",
            excluido_em: "2026-08-01T12:00:00Z",
          },
        ],
        total: 1,
        page: 1,
        page_size: 30,
      },
    } as any);
    postMock.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          detail:
            "Não é possível restaurar enquanto o cliente vinculado estiver na lixeira. Restaure a dependência primeiro.",
        },
      },
    });

    render(<Lixeira />);
    await screen.findByText("Caso dependente");

    fireEvent.click(screen.getByRole("button", { name: /^restaurar$/i }));

    await waitFor(() =>
      expect(erroToast).toHaveBeenCalledWith(
        "Não é possível restaurar enquanto o cliente vinculado estiver na lixeira. Restaure a dependência primeiro.",
      ),
    );
  });
});
