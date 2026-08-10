import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

const mocks = vi.hoisted(() => ({
  role: "estagiario",
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  default: {
    get: mocks.get,
    post: mocks.post,
    patch: mocks.patch,
    delete: mocks.delete,
  },
}));

vi.mock("../stores/auth", () => ({
  useAuth: (selector: (state: { user: { role: string } }) => unknown) =>
    selector({ user: { role: mocks.role } }),
}));

vi.mock("../contexts/useCasoFiltro", () => ({
  useCasoFiltro: () => ({
    casoFiltro: null,
    casoFiltroNome: "",
    removerFiltro: vi.fn(),
  }),
}));

vi.mock("../components/Dashboards", () => ({
  DocumentosStats: () => null,
}));

vi.mock("../components/CaseFilterChip", () => ({
  default: () => null,
}));

vi.mock("../components/Toast", () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
  },
}));

import Documentos from "./Documentos";

const DOCUMENTO = {
  id: "doc-1",
  titulo: "Contrato teste",
  filename: "contrato.pdf",
  tipo: "contrato",
  confidencialidade: "normal",
  size_bytes: 1024,
  case_id: null,
  created_at: "2026-08-10T12:00:00Z",
};

const CASO = {
  id: "case-1",
  numero_interno: "EJC-001",
  titulo: "Caso teste",
  client_id: "client-1",
};

function prepararApi(): void {
  mocks.get.mockImplementation((url: string) => {
    if (url === "/documents/") {
      return Promise.resolve({
        data: { data: [DOCUMENTO], total: 1, page: 1, page_size: 50 },
      });
    }
    if (url === "/cases/") {
      return Promise.resolve({ data: { data: [CASO] } });
    }
    if (url === "/clients/") {
      return Promise.resolve({ data: { data: [] } });
    }
    if (url === "/documents/tipos") {
      return Promise.resolve({ data: { data: [] } });
    }
    return Promise.reject(new Error(`GET inesperado: ${url}`));
  });
  mocks.post.mockResolvedValue({ data: {} });
}

async function renderizarESelecionar(): Promise<void> {
  render(<Documentos />);
  await screen.findByText("Contrato teste");
  fireEvent.click(screen.getByLabelText("Selecionar Contrato teste"));
  await screen.findByText("1 selecionado(s)");
}

beforeEach(() => {
  mocks.role = "estagiario";
  mocks.get.mockReset();
  mocks.post.mockReset();
  mocks.patch.mockReset();
  mocks.delete.mockReset();
  prepararApi();
});

afterEach(cleanup);

describe("Documentos — vínculo com caso", () => {
  it("expõe a ação para papel jurídico autorizado", async () => {
    mocks.role = "estagiario";

    await renderizarESelecionar();

    expect(
      screen.getByRole("button", { name: /Vincular ao caso/i }),
    ).toBeTruthy();
  });

  it("não expõe a ação para papel fora do contrato backend", async () => {
    mocks.role = "financeiro";

    await renderizarESelecionar();

    expect(
      screen.queryByRole("button", { name: /Vincular ao caso/i }),
    ).toBeNull();
  });

  it("usa o POST canônico em vez de PATCH de case_id", async () => {
    mocks.role = "advogado";

    await renderizarESelecionar();
    fireEvent.click(screen.getByRole("button", { name: /Vincular ao caso/i }));

    await screen.findByText(/Vincular ao caso — 1 documento\(s\)/i);
    const seletor = screen
      .getByText("Caso de destino")
      .parentElement?.querySelector("select");
    expect(seletor).not.toBeNull();

    fireEvent.change(seletor as HTMLSelectElement, {
      target: { value: CASO.id },
    });
    fireEvent.click(screen.getByRole("button", { name: "Vincular todos" }));

    await waitFor(() => {
      expect(mocks.post).toHaveBeenCalledWith(
        "/cases/case-1/documentos/doc-1/vincular",
      );
    });
    expect(mocks.patch).not.toHaveBeenCalledWith(
      expect.stringContaining("/documents/doc-1"),
      expect.objectContaining({ case_id: expect.anything() }),
    );
  });
});
