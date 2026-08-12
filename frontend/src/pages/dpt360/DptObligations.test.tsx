// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import type { DptDashboard } from "./api";
import DptObligations from "./DptObligations";

const EMPRESA = {
  id: "c1",
  nome: "Empresa Exemplo S.A.",
  status: "ativo",
  casos: 1,
  casos_abertos: 1,
  sinais_criticos: 0,
  providencias_proximas: 0,
};

function dashboardBase(overrides: Partial<DptDashboard> = {}): DptDashboard {
  return {
    generated_at: "2026-08-12T00:00:00Z",
    metrics: {
      empresas_acompanhadas: 1,
      riscos_criticos: 0,
      providencias_proximas: 0,
      mudancas_juridicas_hoje: null,
      empresas_potencialmente_impactadas: null,
      diagnosticos_pendentes: null,
    },
    companies: [EMPRESA],
    cases: [],
    deadlines: [],
    priorities: [],
    coverage: "complete",
    notes: [],
    ...overrides,
  };
}

describe("DptObligations", () => {
  it("exibe o título da agenda de obrigações", () => {
    render(
      <MemoryRouter>
        <DptObligations data={dashboardBase()} />
      </MemoryRouter>,
    );
    screen.getByText("Agenda de Obrigações Empresariais");
  });

  it("informa que só prazos canônicos vinculados a casos são consolidados", () => {
    render(
      <MemoryRouter>
        <DptObligations data={dashboardBase()} />
      </MemoryRouter>,
    );
    screen.getByText(/a visão consolida somente prazos canônicos/i);
  });

  it("mostra estado vazio quando não há prazos", () => {
    render(
      <MemoryRouter>
        <DptObligations data={dashboardBase()} />
      </MemoryRouter>,
    );
    screen.getByText(/Nenhum prazo empresarial pendente foi localizado/);
  });

  it("lista prazos vinculados ao nome da empresa do caso", () => {
    render(
      <MemoryRouter>
        <DptObligations
          data={dashboardBase({
            cases: [
              {
                id: "k1",
                client_id: "c1",
                titulo: "Caso exemplo",
                area: "tributario",
                status: "em_andamento",
              } as never,
            ],
            deadlines: [
              {
                id: "d1",
                case_id: "k1",
                titulo: "Apresentar contestação",
                data_prazo: "2026-08-20",
                status: "pendente",
              } as never,
            ],
          })}
        />
      </MemoryRouter>,
    );
    screen.getByText("Apresentar contestação");
    screen.getByText(/Empresa Exemplo S\.A\./);
    screen.getByText(/2026-08-20/);
    const link = screen.getByRole("link", { name: /Apresentar contestação/i });
    expect(link.getAttribute("href")).toBe(
      "/atividades?tipo=prazo&caso=k1",
    );
  });
});
