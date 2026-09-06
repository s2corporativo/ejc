// FE-11: renderização da Gestão Documental (abas + Documentos embutido) e os
// estados vazio/erro da listagem que ela hospeda.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

const simulacoes = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  default: {
    get: simulacoes.get,
    post: simulacoes.post,
    patch: simulacoes.patch,
    delete: simulacoes.delete,
  },
  getAccessToken: () => null,
  setAccessToken: vi.fn(),
  refreshAccessToken: vi.fn(),
  logout: vi.fn(),
}));
vi.mock("../stores/auth", () => ({
  useAuth: (selector: (state: { user: { role: string } }) => unknown) =>
    selector({ user: { role: "advogado" } }),
}));
vi.mock("../contexts/useCasoFiltro", () => ({
  useCasoFiltro: () => ({
    casoFiltro: null,
    casoFiltroNome: "",
    removerFiltro: vi.fn(),
  }),
}));
vi.mock("../components/Dashboards", () => ({ DocumentosStats: () => null }));
vi.mock("../components/CaseFilterChip", () => ({ default: () => null }));
vi.mock("../components/Toast", () => ({
  toast: { error: simulacoes.toastError, success: vi.fn(), info: vi.fn() },
}));
// A aba de compartilhamento tem fluxo próprio (testado em DataRoom); aqui só
// interessa que a troca de aba monte o componente certo.
vi.mock("./DataRoom", () => ({
  default: () => <div>DataRoom simulado</div>,
}));

import GestaoDocumental from "./GestaoDocumental";

function prepararApi(documentos: unknown[] | Error): void {
  simulacoes.get.mockImplementation((url: string) => {
    if (url === "/documents/") {
      return documentos instanceof Error
        ? Promise.reject(documentos)
        : Promise.resolve({
            data: {
              data: documentos,
              total: documentos.length,
              page: 1,
              page_size: 50,
            },
          });
    }
    if (
      url === "/cases/" ||
      url === "/clients/" ||
      url === "/documents/tipos"
    ) {
      return Promise.resolve({ data: { data: [] } });
    }
    return Promise.reject(new Error(`GET inesperado: ${url}`));
  });
}

function renderizar(rota = "/documentos") {
  return render(
    <MemoryRouter initialEntries={[rota]}>
      <GestaoDocumental />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  simulacoes.get.mockReset();
  simulacoes.toastError.mockReset();
});
afterEach(() => cleanup());

describe("página /documentos (GestaoDocumental)", () => {
  it("renderiza o cabeçalho e as duas abas, com Documentos ativa por padrão", async () => {
    prepararApi([
      {
        id: "doc-1",
        titulo: "Contrato teste",
        filename: "contrato.pdf",
        tipo: "contrato",
        confidencialidade: "normal",
        size_bytes: 1024,
        case_id: null,
        created_at: "2026-08-10T12:00:00Z",
      },
    ]);
    renderizar();
    expect(screen.getByRole("heading", { name: "Documentos" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /Compartilhamento seguro/ }),
    ).toBeTruthy();
    expect(await screen.findByText("Contrato teste")).toBeTruthy();
  });

  it("estado vazio: lista sem documentos mostra o Empty", async () => {
    prepararApi([]);
    renderizar();
    expect(await screen.findByText("Nenhum documento")).toBeTruthy();
    expect(simulacoes.toastError).not.toHaveBeenCalled();
  });

  it("estado de erro: falha no GET mostra o EmptyState de erro e o toast", async () => {
    prepararApi(new Error("rede"));
    renderizar();
    expect(
      await screen.findByText("Falha ao carregar documentos"),
    ).toBeTruthy();
    expect(simulacoes.toastError).toHaveBeenCalledWith(
      "Falha ao carregar documentos",
    );
  });

  it("?tab=dataroom e o clique na aba alternam para o compartilhamento seguro", async () => {
    prepararApi([]);
    renderizar("/documentos?tab=dataroom");
    expect(await screen.findByText("DataRoom simulado")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /^Documentos$/ }));
    expect(await screen.findByText("Nenhum documento")).toBeTruthy();
  });
});
