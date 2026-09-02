import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";

const simulacoes = vi.hoisted(() => ({
  role: "estagiario",
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
  listInbox: vi.fn(),
  listDocuments: vi.fn(),
  updateMetadata: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  default: {
    get: simulacoes.apiGet,
    post: simulacoes.apiPost,
    patch: simulacoes.apiPatch,
    delete: simulacoes.apiDelete,
  },
}));

vi.mock("../stores/auth", () => ({
  useAuth: (selector: (state: { user: { role: string } }) => unknown) =>
    selector({ user: { role: simulacoes.role } }),
}));

vi.mock("../contexts/useCasoFiltro", () => ({
  useCasoFiltro: () => ({
    casoFiltro: undefined,
    casoFiltroNome: undefined,
    removerFiltro: vi.fn(),
  }),
}));

vi.mock("../components/documents/DocumentWorkflowStats", () => ({
  default: () => null,
}));

vi.mock("../components/documents/DocumentDrawer", () => ({
  default: () => null,
}));

vi.mock("../components/documents/DocumentStatusBadge", () => ({
  default: () => <span>Pronto</span>,
}));

vi.mock("../components/CaseFilterChip", () => ({
  default: () => null,
}));

vi.mock("../components/Toast", () => ({
  toast: {
    error: simulacoes.toastError,
    success: simulacoes.toastSuccess,
    info: vi.fn(),
  },
}));

vi.mock("../services/documents", () => ({
  ATTENTION_LABEL: { sem_caso: "Sem caso vinculado" },
  duplicateDetail: () => null,
  getDocumentBlob: vi.fn(),
  getDocumentPolicy: vi.fn().mockResolvedValue({
    extensions: [".pdf", ".md"],
    max_upload_mb: 25,
    confidentiality: ["normal", "interno", "restrito", "confidencial", "segredo_justica"],
    malware_scan_enabled: false,
  }),
  listDocuments: simulacoes.listDocuments,
  listInbox: simulacoes.listInbox,
  moveDocumentToTrash: vi.fn().mockResolvedValue(undefined),
  updateDocumentMetadata: simulacoes.updateMetadata,
  uploadDocument: vi.fn().mockResolvedValue({}),
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
  versao: 1,
  operational_status: "ready",
  attention_reasons: ["sem_caso"],
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
  titulo: "Caso teste",
  client_id: "client-1",
};

function preparar(documentos = [DOCUMENTO]) {
  const resposta = {
    data: documentos,
    total: documentos.length,
    page: 1,
    page_size: 25,
  };
  simulacoes.listInbox.mockResolvedValue(resposta);
  simulacoes.listDocuments.mockResolvedValue(resposta);
  simulacoes.updateMetadata.mockResolvedValue(DOCUMENTO);
  simulacoes.apiGet.mockImplementation((url: string) => {
    if (url === "/documents/tipos") return Promise.resolve({ data: { data: [] } });
    if (url === "/cases/") return Promise.resolve({ data: { data: [CASO] } });
    if (url === "/clients/") return Promise.resolve({ data: { data: [] } });
    return Promise.reject(new Error(`GET inesperado: ${url}`));
  });
  simulacoes.apiPost.mockResolvedValue({ data: {} });
}

async function renderizar(documentos = [DOCUMENTO]) {
  preparar(documentos);
  render(
    <MemoryRouter>
      <Documentos />
    </MemoryRouter>,
  );
  await screen.findByText("Contrato teste");
}

async function selecionar(titulo = "Contrato teste") {
  fireEvent.click(screen.getByLabelText(`Selecionar ${titulo}`));
  await screen.findByText(/selecionado\(s\)/i);
}

async function seletorCasoDoModal(): Promise<HTMLSelectElement> {
  await screen.findByText(
    "O vínculo é validado pelo backend e respeita cliente, caso e permissões do usuário.",
  );
  const selects = screen.getAllByRole("combobox");
  const modalSelect = selects.at(-1);
  expect(modalSelect).toBeTruthy();
  return modalSelect as HTMLSelectElement;
}

beforeEach(() => {
  simulacoes.role = "estagiario";
  simulacoes.apiGet.mockReset();
  simulacoes.apiPost.mockReset();
  simulacoes.apiPatch.mockReset();
  simulacoes.apiDelete.mockReset();
  simulacoes.listInbox.mockReset();
  simulacoes.listDocuments.mockReset();
  simulacoes.updateMetadata.mockReset();
  simulacoes.toastError.mockReset();
  simulacoes.toastSuccess.mockReset();
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
  ])("expõe vínculo para papel autorizado: %s", async (role) => {
    simulacoes.role = role;
    await renderizar();
    await selecionar();
    expect(screen.getByRole("button", { name: /Vincular ao caso/i })).toBeTruthy();
  });

  it.each(["financeiro", "secretaria", "cliente_externo"])(
    "oculta vínculo para papel fora do contrato: %s",
    async (role) => {
      simulacoes.role = role;
      await renderizar();
      await selecionar();
      expect(screen.queryByRole("button", { name: /Vincular ao caso/i })).toBeNull();
    },
  );
});

describe("Documentos — mutações", () => {
  it("PATCH de metadados não envia case_id", async () => {
    await renderizar();
    fireEvent.click(screen.getByLabelText("Ações de Contrato teste"));
    fireEvent.click(screen.getByRole("button", { name: "Editar metadados" }));

    const titulo = await screen.findByDisplayValue("Contrato teste");
    fireEvent.change(titulo, { target: { value: "Contrato revisado" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => {
      expect(simulacoes.updateMetadata).toHaveBeenCalledWith("doc-1", {
        titulo: "Contrato revisado",
        tipo: "contrato",
        confidencialidade: "normal",
      });
    });
    expect(simulacoes.updateMetadata.mock.calls[0][1]).not.toHaveProperty("case_id");
  });

  it("usa o endpoint canônico de vínculo por documento", async () => {
    simulacoes.role = "advogado";
    await renderizar();
    await selecionar();

    fireEvent.click(screen.getByRole("button", { name: /Vincular ao caso/i }));
    const seletor = await seletorCasoDoModal();
    fireEvent.change(seletor, { target: { value: CASO.id } });
    fireEvent.click(screen.getByRole("button", { name: "Vincular" }));

    await waitFor(() => {
      expect(simulacoes.apiPost).toHaveBeenCalledWith(
        "/cases/case-1/documentos/doc-1/vincular",
      );
    });
  });

  it("mantém falha isolada no vínculo em lote", async () => {
    simulacoes.role = "advogado";
    simulacoes.apiPost.mockResolvedValueOnce({ data: {} }).mockRejectedValueOnce(new Error("falha"));
    await renderizar([DOCUMENTO, DOCUMENTO_2]);
    await selecionar("Contrato teste");
    fireEvent.click(screen.getByLabelText("Selecionar Petição teste"));
    await screen.findByText("2 selecionado(s)");

    fireEvent.click(screen.getByRole("button", { name: /Vincular ao caso/i }));
    const seletor = await seletorCasoDoModal();
    fireEvent.change(seletor, { target: { value: CASO.id } });
    fireEvent.click(screen.getByRole("button", { name: "Vincular" }));

    await waitFor(() => {
      expect(simulacoes.apiPost).toHaveBeenCalledTimes(2);
      expect(simulacoes.toastError).toHaveBeenCalledWith(
        expect.stringContaining("1 vínculo(s) não puderam ser concluídos"),
      );
    });
  });
});
