// @vitest-environment jsdom
import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DptCompany } from "./api";
import DptReports from "./DptReports";
import { getDptExecutiveReport, prepareDptExecutiveReport } from "./reportApi";

vi.mock("./reportApi", () => ({
  getDptExecutiveReport: vi.fn(),
  prepareDptExecutiveReport: vi.fn(),
}));

const getReportMock = vi.mocked(getDptExecutiveReport);
const prepareReportMock = vi.mocked(prepareDptExecutiveReport);

const EMPRESA: DptCompany = {
  id: "c1",
  nome: "Empresa Teste Ltda",
  status: "ativo",
  casos: 1,
  casos_abertos: 1,
  sinais_criticos: 0,
  providencias_proximas: 0,
};

function relatorioBase(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    client_id: "c1",
    empresa: "Empresa Teste Ltda",
    periodo_dias: 30,
    generated_at: "2026-08-12T00:00:00Z",
    status: "rascunho" as const,
    requer_revisao: true,
    cobertura_completa: true,
    cobertura_notas: [],
    situacao_juridica: [],
    principais_riscos: [],
    providencias_futuras: [],
    pendencias: {},
    casos: [],
    mudancas_juridicas_relevantes: [],
    recomendacoes: [],
    proximos_passos: [],
    nota: "",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

async function gerarRelatorio() {
  await act(async () => {
    render(
      <MemoryRouter>
        <DptReports companies={[EMPRESA]} />
      </MemoryRouter>,
    );
  });
  const botao = screen.getByRole("button", { name: /gerar rascunho/i });
  await act(async () => {
    botao.click();
  });
}

describe("DptReports — aviso de cobertura parcial", () => {
  it("não mostra aviso quando a cobertura está completa", async () => {
    getReportMock.mockResolvedValue(
      relatorioBase({ cobertura_completa: true }),
    );
    await gerarRelatorio();
    await waitFor(() =>
      expect(screen.getByText(/Revisão obrigatória/i)).toBeTruthy(),
    );
    expect(screen.queryByText(/Cobertura parcial/i)).toBeNull();
  });

  it("mostra aviso e as notas quando a cobertura está parcial", async () => {
    getReportMock.mockResolvedValue(
      relatorioBase({
        cobertura_completa: false,
        cobertura_notas: ["carteira truncada em 200 empresas"],
      }),
    );
    await gerarRelatorio();
    await waitFor(() =>
      expect(screen.getByText(/Cobertura parcial/i)).toBeTruthy(),
    );
    expect(screen.getByText(/carteira truncada em 200 empresas/)).toBeTruthy();
  });
});


it("prepara documento aprovado sem publicar automaticamente", async () => {
  getReportMock.mockResolvedValue(relatorioBase());
  prepareReportMock.mockResolvedValue({
    document_id: "doc-1",
    client_id: "c1",
    publicado_portal: false,
    next_step: "Publicar depois.",
  });
  vi.spyOn(window, "confirm").mockReturnValue(true);

  await gerarRelatorio();
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /Aprovar e preparar para Portal/i })).toBeTruthy(),
  );
  await act(async () => {
    screen.getByRole("button", { name: /Aprovar e preparar para Portal/i }).click();
  });

  await waitFor(() =>
    expect(prepareReportMock).toHaveBeenCalledWith("c1", 30),
  );
  expect(screen.getByText(/Nenhum envio ao cliente foi feito/i)).toBeTruthy();
});
