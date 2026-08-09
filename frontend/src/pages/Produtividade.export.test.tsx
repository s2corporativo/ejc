// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../lib/api";
import { toast } from "../components/Toast";
import { exportCsv } from "../utils/exportCsv";
import { exportPdf } from "../utils/exportPdf";
import Produtividade from "./Produtividade";

vi.mock("../lib/api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock("../components/Toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

vi.mock("../utils/exportCsv", () => ({ exportCsv: vi.fn() }));
vi.mock("../utils/exportPdf", () => ({ exportPdf: vi.fn() }));

const getMock = vi.mocked(api.get);
const postMock = vi.mocked(api.post);
const csvMock = vi.mocked(exportCsv);
const pdfMock = vi.mocked(exportPdf);
const erroToast = vi.mocked(toast.error);

const dados = (periodo: string) => ({
  periodo,
  desde: "2026-07-10",
  resumo: {
    total_horas: 10,
    horas_faturavel: 8,
    pct_faturavel: 80,
    lancamentos: 2,
  },
  por_advogado: [
    {
      id: "u1",
      nome: "Advogado Teste",
      horas: 10,
      horas_faturavel: 8,
      lancamentos: 2,
      casos: 1,
      pct_faturavel: 80,
    },
  ],
  por_area: [],
  trend: [],
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe("Produtividade — exportação auditada", () => {
  it("desabilita exportação enquanto o novo período ainda não carregou", async () => {
    let resolver!: (value: any) => void;
    const pendente = new Promise((resolve) => {
      resolver = resolve;
    });
    getMock
      .mockResolvedValueOnce({ data: dados("30d") } as any)
      .mockReturnValueOnce(pendente as any);

    render(<Produtividade />);
    await screen.findByText("Advogado Teste");

    fireEvent.click(screen.getByRole("button", { name: "7 dias" }));

    await waitFor(() =>
      expect((screen.getByTitle("Exportar CSV") as HTMLButtonElement).disabled).toBe(
        true,
      ),
    );

    resolver({ data: dados("7d") });
    await waitFor(() =>
      expect((screen.getByTitle("Exportar CSV") as HTMLButtonElement).disabled).toBe(
        false,
      ),
    );
  });

  it("audita e nomeia CSV pelo período do snapshot carregado", async () => {
    getMock.mockResolvedValueOnce({ data: dados("30d") } as any);
    postMock.mockResolvedValueOnce({ data: { ok: true } } as any);

    render(<Produtividade />);
    await screen.findByText("Advogado Teste");
    fireEvent.click(screen.getByTitle("Exportar CSV"));

    await waitFor(() =>
      expect(postMock).toHaveBeenCalledWith(
        "/analytics/produtividade/export-event",
        { periodo: "30d", formato: "csv", linhas: 1 },
      ),
    );
    expect(csvMock).toHaveBeenCalledWith(expect.any(Array), "produtividade-30d");
  });

  it("não registra exportação PDF quando o navegador bloqueia a janela", async () => {
    getMock.mockResolvedValueOnce({ data: dados("30d") } as any);
    vi.spyOn(window, "open").mockReturnValue(null);

    render(<Produtividade />);
    await screen.findByText("Advogado Teste");
    fireEvent.click(screen.getByTitle("Exportar PDF"));

    await waitFor(() => expect(erroToast).toHaveBeenCalled());
    expect(postMock).not.toHaveBeenCalled();
    expect(pdfMock).not.toHaveBeenCalled();
  });

  it("abre popup antes da auditoria e só então gera o PDF na mesma janela", async () => {
    const ordem: string[] = [];
    const janela = {
      document: { title: "" },
      close: vi.fn(),
    } as unknown as Window;
    vi.spyOn(window, "open").mockImplementation(() => {
      ordem.push("popup");
      return janela;
    });
    getMock.mockResolvedValueOnce({ data: dados("30d") } as any);
    postMock.mockImplementationOnce(async () => {
      ordem.push("auditoria");
      return { data: { ok: true } } as any;
    });
    pdfMock.mockImplementationOnce(() => {
      ordem.push("pdf");
      return true;
    });

    render(<Produtividade />);
    await screen.findByText("Advogado Teste");
    fireEvent.click(screen.getByTitle("Exportar PDF"));

    await waitFor(() => expect(pdfMock).toHaveBeenCalled());
    expect(ordem).toEqual(["popup", "auditoria", "pdf"]);
    expect(pdfMock).toHaveBeenCalledWith(
      "Produtividade — 30d",
      expect.any(Array),
      expect.any(Array),
      "produtividade-30d.pdf",
      janela,
    );
  });

  it("fecha a janela reservada quando a auditoria falha", async () => {
    const janela = {
      document: { title: "" },
      close: vi.fn(),
    } as unknown as Window;
    vi.spyOn(window, "open").mockReturnValue(janela);
    getMock.mockResolvedValueOnce({ data: dados("30d") } as any);
    postMock.mockRejectedValueOnce(new Error("falha"));

    render(<Produtividade />);
    await screen.findByText("Advogado Teste");
    fireEvent.click(screen.getByTitle("Exportar PDF"));

    await waitFor(() => expect(janela.close).toHaveBeenCalled());
    expect(pdfMock).not.toHaveBeenCalled();
  });
});
