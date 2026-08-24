// @vitest-environment jsdom
// V2-1.3 (plano-mestre) — filtro de status na listagem de casos.
// Antes, a única forma de restringir por status era o alternador grosso
// ativos/arquivados/todos (`arquivoF`); não havia como pedir só "em_producao"
// ou só "protocolado". O backend já validava e devolvia 422 para status fora
// do enum (nunca mais 500) — faltava só a UI expor os seis valores reais.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";

const getMock = vi.fn();

vi.mock("../lib/api", () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  },
  aplicarExtracao: vi.fn(),
  vincularLoteAoCaso: vi.fn(),
  getAccessToken: () => null,
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

vi.mock("../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import Casos from "./Casos";

function respostaPara(url: string) {
  if (url.startsWith("/cases/")) {
    return Promise.resolve({ data: { data: [], total: 0, page: 1, page_size: 50 } });
  }
  if (url.startsWith("/clients/")) {
    return Promise.resolve({ data: { data: [] } });
  }
  if (url.startsWith("/users/")) {
    return Promise.resolve({ data: { data: [] } });
  }
  if (url.startsWith("/areas")) {
    return Promise.resolve({ data: { areas: [] } });
  }
  return Promise.resolve({ data: {} });
}

beforeEach(() => {
  getMock.mockReset();
  getMock.mockImplementation((url: string) => respostaPara(url));
});

afterEach(() => {
  cleanup();
});

function renderCasos() {
  return render(
    <MemoryRouter initialEntries={["/casos"]}>
      <Casos />
    </MemoryRouter>,
  );
}

describe("Casos — filtro de status", () => {
  it("renderiza os seis status canônicos, sem valor legado (ativo/triagem)", async () => {
    renderCasos();
    const select = await screen.findByTitle("Filtrar por status do caso");
    const rotulos = Array.from(select.querySelectorAll("option")).map(
      (o) => o.textContent,
    );
    expect(rotulos).toEqual([
      "Todos os status",
      "Aberto",
      "Em instrução",
      "Em produção",
      "Protocolado",
      "Encerrado",
      "Arquivado",
    ]);
  });

  it("selecionar um status envia o parâmetro `status` exato para /cases/", async () => {
    renderCasos();
    const select = await screen.findByTitle("Filtrar por status do caso");
    getMock.mockClear();

    fireEvent.change(select, { target: { value: "em_producao" } });

    await waitFor(() => {
      const chamada = getMock.mock.calls.find(
        (c) => typeof c[0] === "string" && c[0].startsWith("/cases/"),
      );
      expect(chamada).toBeTruthy();
      expect(chamada![1]?.params?.status).toBe("em_producao");
    });
  });

  it("voltar para \"Todos os status\" omite o parâmetro — nunca envia sentinela", async () => {
    renderCasos();
    const select = await screen.findByTitle("Filtrar por status do caso");
    getMock.mockClear();
    fireEvent.change(select, { target: { value: "encerrado" } });
    await waitFor(() => {
      const chamada = getMock.mock.calls.find(
        (c) => typeof c[0] === "string" && c[0].startsWith("/cases/"),
      );
      expect(chamada?.[1]?.params?.status).toBe("encerrado");
    });

    getMock.mockClear();
    fireEvent.change(select, { target: { value: "" } });

    await waitFor(() => {
      const chamada = getMock.mock.calls.find(
        (c) => typeof c[0] === "string" && c[0].startsWith("/cases/"),
      );
      expect(chamada).toBeTruthy();
      expect(chamada![1]?.params?.status).toBeUndefined();
    });
  });
});
