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
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
  toastInfo: vi.fn(),
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
    error: mocks.toastError,
    success: mocks.toastSuccess,
    info: mocks.toastInfo,
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

const DOCUMENTO_2 = {
  ...DOCUMENTO,
  id: "doc-2",
  titulo: "Petição teste",
  filename: "peticao.pdf",
  tipo: "peticao",
};

const CASO = {
  id: "case-1",
  numero_interno: "EJC-001",
  titulo: "Caso teste",
  client_id: "client-1",
};

function prepararApi(documentos = [DOCUMENTO]): void {
  mocks.get.mockImplementation((url: string) => {
    if (url === "/documents/") {
      return Promise.resolve({
        data: {
          data: documentos,
          total: documentos.length,
          page: 1,
          page_size: 50,
        },
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
  mocks.patch.mockImplementation((url: string, payload: Record<string, unknown>) =>
    Promise.resolve({
      data: {
        ...DOCUMENTO,
        ...(url === "/documents/doc-1" ? payload : {}),
      },
    }),
  );
}

async function renderizar(): Promise<void> {
  render(<Documentos />);
  await screen.findByText("Contrato teste");
}

async function selecionar(titulo = "Contrato teste"): Promise<void> {
  fireEvent.click(screen.getByLabelText(`Selecionar ${titulo}`));
  await screen.findByText(/selecionado\(s\)/i);
}

async function abrirModalVinculo(): Promise<HTMLSelectElement> {
  fireEvent.click(screen.getByRole("button", { name: /Vincular ao caso/i }));
  await screen.findByText(/Vincular ao caso — .* documento\(s\)/i);
  const seletor = screen
    .getByText("Caso de destino")
    .parentElement?.querySelector("select");
  expect(seletor).not.toBeNull();
  return seletor as HTMLSelectElement;
}

beforeEach(() => {
  mocks.role = "estagiario";
  mocks.get.mockReset();
  mocks.post.mockReset();
  mocks.patch.mockReset();
  mocks.delete.mockReset();
  mocks.toastError.mockReset();
  mocks.toastSuccess.mockReset();
  mocks.toastInfo.mockReset();
  prepararApi();
});

afterEach(cleanup);

describe("Documentos — RBAC de vínculo", () => {
  it.each([
    "superadmin",
    "admin",
    "socio",
    "advogado",
    "advogado_auxiliar",
    "estagiario",
  ])("expõe a ação para papel jurídico autorizado: %s", async (role) => {
    mocks.role = role;

    await renderizar();
    await selecionar();

    expect(
      screen.getByRole("button", { name: /Vincular ao caso/i }),
    ).toBeTruthy();
  });

  it.each(["financeiro", "secretaria", "cliente_externo"])(
    "oculta a ação para papel fora do contrato backend: %s",
    async (role) => {
      mocks.role = role;

      await renderizar();
      await selecionar();

      expect(
        screen.queryByRole("button", { name: /Vincular ao caso/i }),
      ).toBeNull();
    },
  );
});

describe("Documentos — mutações", () => {
  it("PATCH de metadados nunca envia case_id", async () => {
    await renderizar();
    fireEvent.click(screen.getByTitle("Editar metadados"));

    const titulo = await screen.findByDisplayValue("Contrato teste");
    fireEvent.change(titulo, { target: { value: "Contrato revisado" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => {
      expect(mocks.patch).toHaveBeenCalledWith("/documents/doc-1", {
        titulo: "Contrato revisado",
      });
    });
    const payload = mocks.patch.mock.calls[0][1] as Record<string, unknown>;
    expect(payload).not.toHaveProperty("case_id");
  });

  it("usa o POST canônico para vínculo por documento", async () => {
    mocks.role = "advogado";

    await renderizar();
    await selecionar();
    const seletor = await abrirModalVinculo();

    fireEvent.change(seletor, { target: { value: CASO.id } });
    fireEvent.click(screen.getByRole("button", { name: "Vincular todos" }));

    await waitFor(() => {
      expect(mocks.post).toHaveBeenCalledWith(
        "/cases/case-1/documentos/doc-1/vincular",
      );
    });
  });

  it("preserva falha isolada e resume vínculo parcial", async () => {
    mocks.role = "advogado";
    prepararApi([DOCUMENTO, DOCUMENTO_2]);
    mocks.post
      .mockResolvedValueOnce({ data: {} })
      .mockRejectedValueOnce({
        response: { data: { detail: "Documento já vinculado" } },
      });

    await renderizar();
    await selecionar("Contrato teste");
    fireEvent.click(screen.getByLabelText("Selecionar Petição teste"));
    await screen.findByText("2 selecionado(s)");
    const seletor = await abrirModalVinculo();

    fireEvent.change(seletor, { target: { value: CASO.id } });
    fireEvent.click(screen.getByRole("button", { name: "Vincular todos" }));

    await waitFor(() => {
      expect(mocks.post).toHaveBeenNthCalledWith(
        1,
        "/cases/case-1/documentos/doc-1/vincular",
      );
      expect(mocks.post).toHaveBeenNthCalledWith(
        2,
        "/cases/case-1/documentos/doc-2/vincular",
      );
      expect(mocks.toastError).toHaveBeenCalledWith(
        expect.stringContaining("1 vinculado(s), 1 falhou(aram)"),
      );
      expect(mocks.toastError).toHaveBeenCalledWith(
        expect.stringContaining("Documento já vinculado"),
      );
    });
  });
});
