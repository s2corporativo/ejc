// @vitest-environment jsdom
// Admissão automática: cadastrar cliente já emite procuração + contrato de
// honorários no backend. A UI confirma pela listagem real das peças (não pelo
// pressuposto) e oferece o acesso aos rascunhos em papel timbrado.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";

const getMock = vi.fn();
const postMock = vi.fn();
const toastSuccess = vi.fn();
const estado = { role: "advogado" };

vi.mock("../lib/api", () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
    delete: vi.fn().mockResolvedValue({ data: {} }),
    patch: vi.fn().mockResolvedValue({ data: {} }),
  },
  getAccessToken: () => null,
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

vi.mock("../components/Toast", () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: vi.fn(),
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

const PECAS = [
  {
    id: "doc-proc",
    titulo: "Procuracao - Maria Souza",
    tipo: "procuracao",
    status: "rascunho",
    admission_kind: "procuracao_ad_judicia",
    created_at: "2026-09-01T00:00:00Z",
  },
  {
    id: "doc-contrato",
    titulo: "Contrato de Honorarios - Maria Souza",
    tipo: "contrato",
    status: "rascunho",
    admission_kind: "contrato_honorarios",
    created_at: "2026-09-01T00:00:00Z",
  },
];

function montar() {
  return render(
    <MemoryRouter>
      <Clientes />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  estado.role = "advogado";
  getMock.mockReset();
  postMock.mockReset();
  toastSuccess.mockReset();
  getMock.mockImplementation((url: string) => {
    if (url.includes("/pecas-geradas")) {
      return Promise.resolve({ data: PECAS });
    }
    return Promise.resolve({
      data: { data: [CLIENTE], total: 1, page: 1, page_size: 20 },
    });
  });
  postMock.mockResolvedValue({ data: CLIENTE });
});

afterEach(cleanup);

describe("Clientes — documentos de admissão", () => {
  it("cadastro confirma a emissão de procuração e contrato", async () => {
    montar();
    await screen.findByText("Maria Souza");

    fireEvent.click(screen.getByText(/Novo cliente/i));
    fireEvent.click(await screen.findByText(/Salvar cliente/i));

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith("/clients/", expect.anything()),
    );
    await waitFor(() =>
      expect(getMock).toHaveBeenCalledWith("/clients/cli-1/pecas-geradas"),
    );
    await waitFor(() =>
      expect(toastSuccess).toHaveBeenCalledWith(
        expect.stringContaining("Procuração e contrato"),
      ),
    );
  });

  it("lista os rascunhos de admissão do cliente", async () => {
    montar();
    await screen.findByText("Maria Souza");

    fireEvent.click(
      screen.getByTitle("Procuração e contrato de honorários"),
    );

    expect(await screen.findByText("Procuracao - Maria Souza")).toBeTruthy();
    expect(screen.getByText("Contrato de Honorarios - Maria Souza")).toBeTruthy();
  });

  it("regeneração é explícita (forcar_novo) — não duplica em silêncio", async () => {
    montar();
    await screen.findByText("Maria Souza");
    fireEvent.click(screen.getByTitle("Procuração e contrato de honorários"));
    await screen.findByText("Procuracao - Maria Souza");

    fireEvent.click(screen.getByText("Gerar novamente"));
    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith(
        "/clients/cli-1/gerar-documentos",
        { forcar_novo: true },
      ),
    );
  });

  it("papel sem competência jurídica não vê o acesso aos documentos", async () => {
    estado.role = "secretaria";
    montar();
    await screen.findByText("Maria Souza");
    expect(
      screen.queryByTitle("Procuração e contrato de honorários"),
    ).toBeNull();
  });
});
