// @vitest-environment jsdom
// F3.2 (Issue #804) — "vincular documento existente" inline: antes só existia
// como ação em lote no módulo /documentos; agora dá para buscar e vincular
// sem sair da aba de documentos do caso.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

vi.mock("../../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import api from "../../lib/api";
import TabDocumentos from "./TabDocumentos";

describe("TabDocumentos — vincular documento existente", () => {
  beforeEach(() => {
    vi.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/documents/") {
        // GET /documents/?case_id=case-1 (lista da aba) — sem params de busca.
        return Promise.resolve({ data: { data: [] } });
      }
      return Promise.resolve({ data: {} });
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("busca documentos com debounce e exclui os já vinculados a este caso", async () => {
    const get = vi.spyOn(api, "get").mockImplementation((url, config) => {
      if (url === "/documents/" && (config as any)?.params?.search) {
        return Promise.resolve({
          data: {
            data: [
              { id: "d1", titulo: "Petição inicial", case_id: null },
              { id: "d2", titulo: "Já é deste caso", case_id: "case-1" },
            ],
          },
        });
      }
      return Promise.resolve({ data: { data: [] } });
    });

    render(<TabDocumentos caseId="case-1" />);

    fireEvent.change(
      screen.getByPlaceholderText("Buscar documento por título…"),
      { target: { value: "petição" } },
    );

    await waitFor(
      () => {
        expect(screen.getByText("Petição inicial")).toBeTruthy();
      },
      { timeout: 1000 },
    );
    // O documento já vinculado A ESTE caso não aparece como resultado.
    expect(screen.queryByText("Já é deste caso")).toBeNull();
    expect(get).toHaveBeenCalledWith(
      "/documents/",
      expect.objectContaining({
        params: expect.objectContaining({ search: "petição" }),
      }),
    );
  });

  it("vincular chama PATCH /documents/{id} com o case_id e recarrega a lista", async () => {
    vi.spyOn(api, "get").mockImplementation((url, config) => {
      if (url === "/documents/" && (config as any)?.params?.search) {
        return Promise.resolve({
          data: {
            data: [{ id: "d1", titulo: "Contrato social", case_id: null }],
          },
        });
      }
      return Promise.resolve({ data: { data: [] } });
    });
    const patch = vi.spyOn(api, "patch").mockResolvedValue({ data: {} });

    render(<TabDocumentos caseId="case-1" />);

    fireEvent.change(
      screen.getByPlaceholderText("Buscar documento por título…"),
      { target: { value: "contrato" } },
    );
    await waitFor(() => {
      expect(screen.getByText("Contrato social")).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: /Vincular/ }));

    await waitFor(() => {
      expect(patch).toHaveBeenCalledWith("/documents/d1", {
        case_id: "case-1",
      });
    });
    // Busca limpa após vincular (o resultado some).
    await waitFor(() => {
      expect(screen.queryByText("Contrato social")).toBeNull();
    });
  });

  it("avisa quando o documento encontrado já está vinculado a OUTRO caso", async () => {
    vi.spyOn(api, "get").mockImplementation((url, config) => {
      if (url === "/documents/" && (config as any)?.params?.search) {
        return Promise.resolve({
          data: {
            data: [{ id: "d1", titulo: "Procuração", case_id: "outro-caso" }],
          },
        });
      }
      return Promise.resolve({ data: { data: [] } });
    });

    render(<TabDocumentos caseId="case-1" />);
    fireEvent.change(
      screen.getByPlaceholderText("Buscar documento por título…"),
      { target: { value: "procuração" } },
    );

    await waitFor(() => {
      expect(screen.getByText(/Já vinculado a outro caso/)).toBeTruthy();
    });
  });
});
