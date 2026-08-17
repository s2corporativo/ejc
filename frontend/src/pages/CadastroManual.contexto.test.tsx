// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
import api from "../lib/api";
import { useCadastroManualStore } from "../stores/cadastroManual";
import CadastroManual from "./CadastroManual";

vi.mock("../stores/auth", () => ({
  useAuth: (selector: (state: unknown) => unknown) =>
    selector({ user: { id: "secretaria-1", role: "secretaria" } }),
}));

vi.mock("../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

function campoPorRotulo(rotulo: string, seletor: "input" | "select") {
  const label = screen.getByText(rotulo);
  const campo = label.parentElement?.querySelector(seletor);
  if (!campo) throw new Error(`Campo não encontrado para: ${rotulo}`);
  return campo as HTMLInputElement | HTMLSelectElement;
}

describe("CadastroManual — cliente fixado pela Ficha Mestra", () => {
  beforeEach(() => {
    localStorage.clear();
    useCadastroManualStore.setState({
      rascunhoCliente: {},
      rascunhoCaso: {},
      fila: [],
      clientesCache: [],
      usuarioId: null,
      sincronizando: false,
    });
    vi.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/clients/c1") {
        return Promise.resolve({
          data: { id: "c1", nome: "Cliente Existente" },
        });
      }
      if (url === "/clients/") {
        return Promise.resolve({
          data: { data: [{ id: "c1", nome: "Cliente Existente" }] },
        });
      }
      return Promise.resolve({ data: {} });
    });
    vi.spyOn(api, "post").mockResolvedValue({ data: { id: "case-1" } });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("valida o cliente, abre Novo caso e não permite trocar o vínculo", async () => {
    render(
      <MemoryRouter initialEntries={["/entrada?client_id=c1&modo=manual"]}>
        <CadastroManual />
      </MemoryRouter>,
    );

    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/clients/c1"));
    expect(
      screen.getByText(/Cliente definido pela Ficha Mestra/i),
    ).toBeTruthy();
    expect(screen.queryByText("+ Criar cliente novo junto")).toBeNull();

    const selectCliente = campoPorRotulo("Cliente *", "select");
    expect(selectCliente.disabled).toBe(true);
    expect(selectCliente.value).toBe("c1");
  });

  it("envia o caso usando o client_id autorizado, sem criar outro cliente", async () => {
    render(
      <MemoryRouter initialEntries={["/entrada?client_id=c1&modo=manual"]}>
        <CadastroManual />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByText(/Vínculo validado pelo backend/i)).toBeTruthy(),
    );

    fireEvent.change(campoPorRotulo("Título do caso *", "input"), {
      target: { value: "Caso contextual" },
    });
    fireEvent.change(campoPorRotulo("Próxima ação *", "input"), {
      target: { value: "Revisar documentos" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Abrir caso" }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        "/cases/",
        expect.objectContaining({
          titulo: "Caso contextual",
          client_id: "c1",
          proxima_acao: "Revisar documentos",
        }),
      );
    });
    expect(api.post).not.toHaveBeenCalledWith("/clients/", expect.anything());
  });
});
