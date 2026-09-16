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
  within,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";

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
    <MemoryRouter initialEntries={["/clientes"]}>
      <Routes>
        <Route path="/clientes" element={<Clientes />} />
        <Route path="/clientes/:id" element={<div>FICHA DESTINO</div>} />
      </Routes>
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

  it("navega para a Ficha Mestra sem esperar a confirmação acessória", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/clients/cli-1/pecas-geradas") {
        return new Promise(() => {});
      }
      return Promise.resolve({
        data: { data: [CLIENTE], total: 1, page: 1, page_size: 20 },
      });
    });

    montar();
    await screen.findByText("Maria Souza");
    fireEvent.click(screen.getByText(/Novo cliente/i));
    fireEvent.click(await screen.findByText(/Salvar cliente/i));

    expect(await screen.findByText("FICHA DESTINO")).toBeTruthy();
    expect(getMock).toHaveBeenCalledWith("/clients/cli-1/pecas-geradas");
  });

  it("falha da checagem de conflito é explícita e resetada ao reabrir", async () => {
    postMock.mockImplementation((url: string) => {
      if (url === "/clients/checar-conflito") {
        return Promise.reject(new Error("serviço indisponível"));
      }
      return Promise.resolve({ data: CLIENTE });
    });

    montar();
    await screen.findByText("Maria Souza");
    fireEvent.click(screen.getByText(/Novo cliente/i));

    const dialog = await screen.findByRole("dialog");
    const parteContraria = within(dialog)
      .getByText(/Parte contrária/i)
      .parentElement?.querySelector("input");
    expect(parteContraria).toBeTruthy();
    fireEvent.change(parteContraria!, { target: { value: "Empresa Adversa" } });
    fireEvent.blur(parteContraria!);

    expect(
      await screen.findByText("Conflito não pôde ser verificado"),
    ).toBeTruthy();

    fireEvent.click(within(dialog).getByRole("button", { name: "Fechar" }));
    fireEvent.click(screen.getByText(/Novo cliente/i));

    expect(screen.queryByText("Conflito não pôde ser verificado")).toBeNull();
  });

  it("lista os rascunhos de admissão do cliente", async () => {
    montar();
    await screen.findByText("Maria Souza");

    fireEvent.click(screen.getByTitle("Procuração e contrato de honorários"));

    expect(await screen.findByText("Procuracao - Maria Souza")).toBeTruthy();
    expect(
      screen.getByText("Contrato de Honorarios - Maria Souza"),
    ).toBeTruthy();
  });

  it("regeneração é explícita (forcar_novo) e carrega os poderes escolhidos", async () => {
    // Regressão: enviar só `forcar_novo` faria o backend aplicar os defaults e
    // trocar o mandato — a procuração emitida com ad_judicia_et_extra voltaria
    // como ad_judicia, e o cliente assinaria poderes que ninguém escolheu.
    montar();
    await screen.findByText("Maria Souza");
    fireEvent.click(screen.getByTitle("Procuração e contrato de honorários"));
    await screen.findByText("Procuracao - Maria Souza");

    fireEvent.change(screen.getByDisplayValue("Ad judicia (foro em geral)"), {
      target: { value: "ad_judicia_et_extra" },
    });
    fireEvent.click(screen.getByText("Gerar novamente"));

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith("/clients/cli-1/gerar-documentos", {
        forcar_novo: true,
        tipo_poderes: "ad_judicia_et_extra",
        permite_substabelecimento: true,
        poderes_especiais: null,
      }),
    );
  });

  it("resposta obsoleta não vaza documentos de outro cliente", async () => {
    // Regressão: a resposta lenta de A chegando depois da abertura de B
    // sobrescrevia a lista, e os botões baixavam as peças de A no modal de B.
    const OUTRO = { ...CLIENTE, id: "cli-2", nome: "João Lima" };
    let resolverA: ((v: unknown) => void) | null = null;

    getMock.mockImplementation((url: string) => {
      if (url === "/clients/cli-1/pecas-geradas") {
        return new Promise((r) => {
          resolverA = () => r({ data: PECAS });
        });
      }
      if (url === "/clients/cli-2/pecas-geradas") {
        return Promise.resolve({ data: [] });
      }
      return Promise.resolve({
        data: { data: [CLIENTE, OUTRO], total: 2, page: 1, page_size: 20 },
      });
    });

    montar();
    await screen.findByText("Maria Souza");
    const botoes = screen.getAllByTitle("Procuração e contrato de honorários");

    fireEvent.click(botoes[0]); // A — fica pendente
    fireEvent.click(botoes[1]); // B — resolve primeiro
    await screen.findByText(/Nenhum documento de admissão/i);

    resolverA?.(null); // resposta obsoleta de A chega por último
    await waitFor(() =>
      expect(screen.queryByText("Procuracao - Maria Souza")).toBeNull(),
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
