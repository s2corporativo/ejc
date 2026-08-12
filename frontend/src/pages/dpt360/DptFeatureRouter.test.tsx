// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DptDashboard } from "./api";
import DptFeatureRouter from "./DptFeatureRouter";

vi.mock("./DptIntelligence", () => ({
  default: () => <div data-testid="dpt-intelligence">Motor Jurídico</div>,
}));
vi.mock("./DptDiagnosis", () => ({
  default: () => <div data-testid="dpt-diagnosis">Diagnóstico</div>,
}));
vi.mock("./DptRadar", () => ({
  default: () => <div data-testid="dpt-radar">Radar</div>,
}));
vi.mock("./DptTools", () => ({
  default: () => <div data-testid="dpt-tools">Ferramentas</div>,
}));
vi.mock("./DptObligations", () => ({
  default: () => <div data-testid="dpt-obligations">Obrigações</div>,
}));
vi.mock("./DptOpportunities", () => ({
  default: () => <div data-testid="dpt-opportunities">Oportunidades</div>,
}));
vi.mock("./DptReports", () => ({
  default: () => <div data-testid="dpt-reports">Relatórios</div>,
}));

const DASHBOARD: DptDashboard = {
  generated_at: "2026-08-12T00:00:00Z",
  metrics: {
    empresas_acompanhadas: 0,
    riscos_criticos: 0,
    providencias_proximas: 0,
    mudancas_juridicas_hoje: null,
    empresas_potencialmente_impactadas: null,
    diagnosticos_pendentes: null,
  },
  companies: [],
  cases: [],
  deadlines: [],
  priorities: [],
  coverage: "complete",
  notes: [],
};

function renderRouter(name: string) {
  return render(
    <MemoryRouter>
      <DptFeatureRouter name={name} data={DASHBOARD} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("DptFeatureRouter", () => {
  it("roteia 'inteligencia' para o Motor Jurídico", () => {
    renderRouter("inteligencia");
    screen.getByTestId("dpt-intelligence");
  });

  it("roteia 'diagnostico' para o Diagnóstico", () => {
    renderRouter("diagnostico");
    screen.getByTestId("dpt-diagnosis");
  });

  it("roteia 'radar' para o Radar", () => {
    renderRouter("radar");
    screen.getByTestId("dpt-radar");
  });

  it("roteia 'ferramentas' para Ferramentas", () => {
    renderRouter("ferramentas");
    screen.getByTestId("dpt-tools");
  });

  it("roteia 'obrigacoes' para Obrigações", () => {
    renderRouter("obrigacoes");
    screen.getByTestId("dpt-obligations");
  });

  it("roteia 'oportunidades' para Oportunidades", () => {
    renderRouter("oportunidades");
    screen.getByTestId("dpt-opportunities");
  });

  it("roteia 'relatorios' para Relatórios", () => {
    renderRouter("relatorios");
    screen.getByTestId("dpt-reports");
  });

  it("exibe a Biblioteca Empresarial planejada com link para o Conhecimento", () => {
    renderRouter("biblioteca");
    screen.getByText("Biblioteca Empresarial");
    const link = screen.getByRole("link", { name: /Abrir Conhecimento/i });
    expect(link.getAttribute("href")).toBe("/inteligencia?tab=conhecimento");
  });

  it("exibe erro de governança para funcionalidade inexistente", () => {
    renderRouter("inexistente");
    screen.getByText(/Funcionalidade DPT não encontrada/);
  });
});
