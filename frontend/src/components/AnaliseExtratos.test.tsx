// FE-01: o HTML da minuta gerada pelo backend abre numa aba nova via
// Blob + URL.createObjectURL, nunca por document.write numa janela about:blank.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

const simulacoes = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  toastInfo: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  default: { post: simulacoes.post, get: simulacoes.get },
  getAccessToken: () => null,
  setAccessToken: vi.fn(),
  refreshAccessToken: vi.fn(),
  logout: vi.fn(),
}));
vi.mock("../lib/stream", () => ({ authFetch: vi.fn() }));
vi.mock("./Toast", () => ({
  toast: {
    info: simulacoes.toastInfo,
    error: simulacoes.toastError,
    success: vi.fn(),
  },
}));

import AnaliseExtratos, { abrirHtmlEmNovaAba } from "./AnaliseExtratos";

const HTML =
  "<html><body><h1>Notificação</h1><script>alert(1)</script></body></html>";

let createObjectURL: ReturnType<typeof vi.fn>;
let revokeObjectURL: ReturnType<typeof vi.fn>;
let open: ReturnType<typeof vi.fn>;

beforeEach(() => {
  createObjectURL = vi.fn(() => "blob:http://localhost/abc");
  revokeObjectURL = vi.fn();
  open = vi.fn(() => ({ document: { write: vi.fn() } }));
  Object.defineProperty(URL, "createObjectURL", {
    value: createObjectURL,
    configurable: true,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    value: revokeObjectURL,
    configurable: true,
  });
  vi.spyOn(window, "open").mockImplementation(
    open as unknown as typeof window.open,
  );
  simulacoes.post.mockReset();
  simulacoes.toastInfo.mockReset();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("abrirHtmlEmNovaAba (FE-01)", () => {
  it("cria um Blob text/html, abre por objectURL com noopener e revoga depois", () => {
    // Timers falsos só aqui (a revogação é agendada); com `waitFor` no teste
    // de componente eles travariam a espera.
    vi.useFakeTimers();
    expect(abrirHtmlEmNovaAba(HTML)).toBe(true);

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    const blob = createObjectURL.mock.calls[0][0] as Blob;
    expect(blob).toBeInstanceOf(Blob);
    expect(blob.type).toBe("text/html;charset=utf-8");

    expect(open).toHaveBeenCalledWith(
      "blob:http://localhost/abc",
      "_blank",
      "noopener,noreferrer",
    );
    // Nada de document.write na janela aberta.
    const janela = open.mock.results[0].value as {
      document: { write: unknown };
    };
    expect(janela.document.write).not.toHaveBeenCalled();

    expect(revokeObjectURL).not.toHaveBeenCalled();
    vi.advanceTimersByTime(60_000);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:http://localhost/abc");
    vi.useRealTimers();
  });

  it("avisa quando o navegador bloqueia o pop-up", () => {
    open.mockReturnValueOnce(null);
    expect(abrirHtmlEmNovaAba(HTML)).toBe(false);
    expect(simulacoes.toastInfo).toHaveBeenCalledWith(
      "Permita pop-ups para visualizar o documento gerado.",
    );
  });
});

describe("AnaliseExtratos · gerar documento", () => {
  it("após o upload, o botão Notificação pede o HTML e abre via Blob", async () => {
    simulacoes.post.mockImplementation((url: string) => {
      if (url === "/bank-analysis/upload") {
        return Promise.resolve({
          data: {
            analise: {
              id: "an-1",
              total_transacoes: 3,
              total_debitos: 100,
              qtd_abusivas: 0,
              total_abusivo: 0,
            },
            cobrancas: [],
          },
        });
      }
      if (url === "/bank-analysis/an-1/documento") {
        return Promise.resolve({ data: { html: HTML } });
      }
      return Promise.reject(new Error(`POST inesperado: ${url}`));
    });

    const { container } = render(<AnaliseExtratos />);
    const input = container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const arquivo = new File(["x"], "extrato.csv", { type: "text/csv" });
    fireEvent.change(input, { target: { files: [arquivo] } });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Notificação/ })).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: /Notificação/ }));

    await waitFor(() => {
      expect(simulacoes.post).toHaveBeenCalledWith(
        "/bank-analysis/an-1/documento",
        { tipo: "notificacao" },
      );
      expect(open).toHaveBeenCalledWith(
        "blob:http://localhost/abc",
        "_blank",
        "noopener,noreferrer",
      );
    });
    expect(createObjectURL).toHaveBeenCalledTimes(1);
  });
});
