// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import api from "../../lib/api";
import TabDocumentos from "./TabDocumentos";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

describe("TabDocumentos — vínculo canônico", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(api, "get").mockResolvedValue({ data: { data: [] } });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("busca candidatos no endpoint do caso e vincula por POST de domínio", async () => {
    const get = vi.spyOn(api, "get").mockImplementation((url) => {
      if (String(url).includes("/documentos/candidatos")) {
        return Promise.resolve({
          data: {
            data: [{ id: "d1", titulo: "Contrato social", case_id: null }],
            total: 1,
          },
        });
      }
      return Promise.resolve({ data: { data: [] } });
    });
    const post = vi.spyOn(api, "post").mockResolvedValue({
      data: { ok: true, alterado: true, status_caso_avancou: true },
    });

    render(<TabDocumentos caseId="case-1" />);
    fireEvent.change(
      screen.getByPlaceholderText("Buscar documento por título ou arquivo…"),
      { target: { value: "contrato" } },
    );
    await act(async () => {
      vi.advanceTimersByTime(450);
      await Promise.resolve();
    });

    expect(screen.getByText("Contrato social")).toBeTruthy();
    expect(get).toHaveBeenCalledWith(
      "/cases/case-1/documentos/candidatos",
      expect.objectContaining({
        params: { search: "contrato", page: 1, page_size: 20 },
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: /Vincular/ }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(post).toHaveBeenCalledWith("/cases/case-1/documentos/d1/vincular");
  });

  it("não oferece movimento se uma resposta inesperada trouxer documento de outro caso", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { ok: true } });
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (String(url).includes("/documentos/candidatos")) {
        return Promise.resolve({
          data: {
            data: [
              {
                id: "d-outro",
                titulo: "Documento de outro caso",
                case_id: "case-origem",
              },
            ],
            total: 1,
          },
        });
      }
      return Promise.resolve({ data: { data: [] } });
    });

    render(<TabDocumentos caseId="case-1" />);
    fireEvent.change(
      screen.getByPlaceholderText("Buscar documento por título ou arquivo…"),
      { target: { value: "documento" } },
    );
    await act(async () => {
      vi.advanceTimersByTime(450);
      await Promise.resolve();
    });

    expect(screen.getByText("Documento de outro caso")).toBeTruthy();
    expect(screen.getByText(/evidência original não pode ser movida/i)).toBeTruthy();
    const indisponivel = screen.getByRole("button", { name: "Indisponível" });
    expect((indisponivel as HTMLButtonElement).disabled).toBe(true);
    expect(post).not.toHaveBeenCalled();
  });

  it("não deixa resposta antiga sobrescrever a busca mais recente", async () => {
    const antiga = deferred<any>();
    const nova = deferred<any>();
    vi.spyOn(api, "get").mockImplementation((url, config) => {
      if (!String(url).includes("/documentos/candidatos")) {
        return Promise.resolve({ data: { data: [] } });
      }
      return (config as any)?.params?.search === "antiga"
        ? antiga.promise
        : nova.promise;
    });

    render(<TabDocumentos caseId="case-1" />);
    const input = screen.getByPlaceholderText(
      "Buscar documento por título ou arquivo…",
    );
    fireEvent.change(input, { target: { value: "antiga" } });
    await act(async () => vi.advanceTimersByTime(450));
    fireEvent.change(input, { target: { value: "nova" } });
    await act(async () => vi.advanceTimersByTime(450));

    await act(async () => {
      nova.resolve({
        data: { data: [{ id: "n", titulo: "Resultado novo" }], total: 1 },
      });
      await Promise.resolve();
    });
    expect(screen.getByText("Resultado novo")).toBeTruthy();

    await act(async () => {
      antiga.resolve({
        data: { data: [{ id: "a", titulo: "Resultado antigo" }], total: 1 },
      });
      await Promise.resolve();
    });
    expect(screen.queryByText("Resultado antigo")).toBeNull();
    expect(screen.getByText("Resultado novo")).toBeTruthy();
  });

  it("mostra erro de busca e permite tentar novamente", async () => {
    let tentativas = 0;
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (!String(url).includes("/documentos/candidatos")) {
        return Promise.resolve({ data: { data: [] } });
      }
      tentativas += 1;
      if (tentativas === 1) return Promise.reject(new Error("offline"));
      return Promise.resolve({
        data: {
          data: [{ id: "d2", titulo: "Procuração recuperada" }],
          total: 1,
        },
      });
    });

    render(<TabDocumentos caseId="case-1" />);
    fireEvent.change(
      screen.getByPlaceholderText("Buscar documento por título ou arquivo…"),
      { target: { value: "procuração" } },
    );
    await act(async () => {
      vi.advanceTimersByTime(450);
      await Promise.resolve();
    });

    expect(
      screen.getByText("Não foi possível buscar documentos disponíveis."),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    await act(async () => {
      vi.advanceTimersByTime(450);
      await Promise.resolve();
    });
    expect(screen.getByText("Procuração recuperada")).toBeTruthy();
  });

  it("avisa quando há mais resultados server-side do que a primeira página", async () => {
    vi.spyOn(api, "get").mockImplementation((url) => {
      if (String(url).includes("/documentos/candidatos")) {
        return Promise.resolve({
          data: { data: [{ id: "d1", titulo: "Petição" }], total: 37 },
        });
      }
      return Promise.resolve({ data: { data: [] } });
    });
    render(<TabDocumentos caseId="case-1" />);
    fireEvent.change(
      screen.getByPlaceholderText("Buscar documento por título ou arquivo…"),
      { target: { value: "pet" } },
    );
    await act(async () => {
      vi.advanceTimersByTime(450);
      await Promise.resolve();
    });
    expect(screen.getByText(/37 documentos correspondem à busca/)).toBeTruthy();
  });
});
