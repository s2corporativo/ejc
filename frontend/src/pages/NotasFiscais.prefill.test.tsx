// @vitest-environment jsdom
// Plano ERP/agenda/IA (achado E3): vindo de Honorários, o formulário de registro
// da NFS-e abre preenchido com honorário, cliente, valor e descrição.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

const get = vi.fn();
vi.mock("../lib/api", () => ({
  default: { get: (...a: unknown[]) => get(...a), post: vi.fn() },
}));
vi.mock("../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import NotasFiscais from "./NotasFiscais";

describe("NFS-e — formulário preenchido a partir do recebimento", () => {
  beforeEach(() => {
    get.mockImplementation((url: string) => {
      if (url === "/nfse/status") {
        return Promise.resolve({ data: { enabled: false, manual_disponivel: true } });
      }
      if (url === "/nfse") return Promise.resolve({ data: { items: [], total: 0 } });
      return Promise.resolve({ data: { data: [] } });
    });
  });
  afterEach(() => {
    cleanup();
    get.mockReset();
  });

  it("abre o modal com os dados do honorário recebido", async () => {
    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: "/financeiro",
            search: "?tab=nfse",
            state: {
              notaDoHonorario: {
                fee_id: "fee-1",
                client_id: "cli-1",
                valor: "1500",
                descricao: "Honorários contratuais — parcela 1",
              },
            },
          },
        ]}
      >
        <NotasFiscais />
      </MemoryRouter>,
    );
    expect(await screen.findByDisplayValue("1500")).toBeTruthy();
    expect(screen.getByDisplayValue("Honorários contratuais — parcela 1")).toBeTruthy();
  });

  it("sem pedido no state o modal não abre sozinho", async () => {
    render(
      <MemoryRouter initialEntries={["/financeiro?tab=nfse"]}>
        <NotasFiscais />
      </MemoryRouter>,
    );
    await screen.findAllByText(/Registrar nota emitida/);
    expect(screen.queryByDisplayValue("1500")).toBeNull();
  });
});
