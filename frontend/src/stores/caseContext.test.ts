// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import api from "../lib/api";
import { getUltimoCasoId, useCaseContext } from "./caseContext";

vi.mock("../lib/api", () => ({
  default: {
    get: vi.fn(),
  },
}));

describe("caseContext — próxima ação persistente", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    useCaseContext.setState({ caso: null });
    vi.clearAllMocks();
  });

  it("carrega e persiste próxima ação e prazo do caso ativo", async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/cases/caso-1") {
        return Promise.resolve({
          data: {
            id: "caso-1",
            titulo: "Empresa X × Empresa Y",
            client_id: "cliente-1",
            numero_processo: "0000000-00.2026.8.13.0000",
            proxima_acao: "Protocolar manifestação",
            proxima_acao_prazo: "2026-09-05T12:00:00-03:00",
          },
        } as never);
      }
      if (url === "/clients/cliente-1") {
        return Promise.resolve({ data: { nome: "Empresa X" } } as never);
      }
      return Promise.reject(new Error(`URL inesperada: ${url}`));
    });

    await useCaseContext.getState().ativar("caso-1");

    const caso = useCaseContext.getState().caso;
    expect(caso?.proxima_acao).toBe("Protocolar manifestação");
    expect(caso?.proxima_acao_prazo).toBe("2026-09-05T12:00:00-03:00");

    const salvo = JSON.parse(sessionStorage.getItem("ejc_caso_ativo") || "{}");
    expect(salvo.proxima_acao).toBe("Protocolar manifestação");
    expect(salvo.proxima_acao_prazo).toBe("2026-09-05T12:00:00-03:00");
    expect(getUltimoCasoId()).toBe("caso-1");
  });

  it("mantém o último caso mesmo após sair do modo caso", async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { id: "caso-2", titulo: "Caso persistente" },
    } as never);

    await useCaseContext.getState().ativar("caso-2");
    useCaseContext.getState().sair();

    expect(useCaseContext.getState().caso).toBeNull();
    expect(sessionStorage.getItem("ejc_caso_ativo")).toBeNull();
    expect(getUltimoCasoId()).toBe("caso-2");
  });
});
