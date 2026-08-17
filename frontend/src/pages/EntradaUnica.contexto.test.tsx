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

let role = "advogado";
const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("../stores/auth", () => ({
  useAuth: () => ({ user: { id: "u1", role, full_name: "Usuário" } }),
}));

vi.mock("../lib/api", () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}));

vi.mock("../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock("./CadastroManual", () => ({
  default: () => <div data-testid="cadastro-manual">Cadastro manual</div>,
}));

vi.mock("./EntradaUnica/TelaEnvio", () => ({
  TelaInicial: ({ onAnalisar }: { onAnalisar: () => void }) => (
    <button onClick={onAnalisar}>analisar-test</button>
  ),
  TelaAnalisando: () => <div>Analisando</div>,
}));

vi.mock("./EntradaUnica/Confirmacao", () => ({
  Confirmacao: ({ proposta }: { proposta: { clienteId?: string | null } }) => (
    <div data-testid="cliente-confirmacao">
      {proposta.clienteId || "sem-cliente"}
    </div>
  ),
}));

import EntradaUnica from "./EntradaUnica";

beforeEach(() => {
  role = "advogado";
  sessionStorage.clear();
  getMock.mockReset();
  postMock.mockReset();
  getMock.mockImplementation((url: string) => {
    if (url === "/clients/c1") {
      return Promise.resolve({
        data: { id: "c1", nome: "Cliente Autorizado" },
      });
    }
    if (url === "/entrada-universal/meta") return Promise.resolve({ data: {} });
    if (url === "/users/") return Promise.resolve({ data: [] });
    return Promise.resolve({ data: {} });
  });
  postMock.mockResolvedValue({
    data: {
      rascunho_id: "r1",
      cliente: { client_id: "outro", nome: "Inferido pela IA" },
      area: {},
      documentos: [],
    },
  });
});

afterEach(cleanup);

describe("Entrada Jurídica — contexto e RBAC", () => {
  it("mantém secretaria na mesma porta, mas em modo manual", () => {
    role = "secretaria";
    render(
      <MemoryRouter initialEntries={["/entrada"]}>
        <EntradaUnica />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("cadastro-manual")).toBeTruthy();
    expect(screen.queryByText("analisar-test")).toBeNull();
  });

  it("não inicia a IA enquanto o client_id da URL ainda não foi validado", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/clients/c1") return new Promise(() => {});
      if (url === "/entrada-universal/meta")
        return Promise.resolve({ data: {} });
      return Promise.resolve({ data: {} });
    });

    render(
      <MemoryRouter initialEntries={["/entrada?client_id=c1"]}>
        <EntradaUnica />
      </MemoryRouter>,
    );

    await waitFor(() => expect(getMock).toHaveBeenCalledWith("/clients/c1"));
    fireEvent.click(screen.getByText("analisar-test"));
    expect(postMock).not.toHaveBeenCalled();
  });

  it("revalida client_id no backend e ele vence cliente inferido pela IA", async () => {
    render(
      <MemoryRouter initialEntries={["/entrada?client_id=c1"]}>
        <EntradaUnica />
      </MemoryRouter>,
    );

    await waitFor(() => expect(getMock).toHaveBeenCalledWith("/clients/c1"));
    await waitFor(() => screen.getByText("analisar-test"));
    fireEvent.click(screen.getByText("analisar-test"));

    await waitFor(() =>
      expect(screen.getByTestId("cliente-confirmacao").textContent).toBe("c1"),
    );
  });
});
