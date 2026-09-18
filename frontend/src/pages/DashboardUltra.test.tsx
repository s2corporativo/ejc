// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

const getMock = vi.fn();
let papelAtual = "advogado";

vi.mock("../lib/api", () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
  },
}));

vi.mock("../stores/auth", () => ({
  useAuth: (
    selector: (state: { user: { role: string; full_name: string } }) => unknown,
  ) => selector({ user: { role: papelAtual, full_name: "Clovis Teste" } }),
}));

vi.mock("../config/officeBranding", () => ({
  officeBranding: {
    officeName: "Marca Jurídica Configurada",
  },
  getWhatsAppUrl: () => "",
  getMailtoUrl: () => "",
}));

vi.mock("./EntradaUnica", () => ({
  EntradaInteligente: ({ embedded }: { embedded?: boolean }) => (
    <div data-testid="entrada-unica" data-embedded={String(Boolean(embedded))}>
      Entrada Única embutida
    </div>
  ),
}));

vi.mock("../components/JurisprudentialAlertsStrip", () => ({
  default: () => <div aria-label="Radar Jurídico">Radar Jurídico</div>,
}));

import DashboardUltra from "./DashboardUltra";

const alertasOk = {
  resumo: {
    prazo: { ativos: 2, novos: 1, criticos: 1, altos: 1 },
    tarefa: { ativos: 1, novos: 1, criticos: 0, altos: 1 },
    intimacao: { ativos: 1, novos: 1, criticos: 0, altos: 1 },
    movimentacao: { ativos: 1, novos: 1, criticos: 0, altos: 1 },
  },
};

function mockGetOk() {
  getMock.mockImplementation((url: string) => {
    if (url === "/atividades/alertas-inteligentes") {
      return Promise.resolve({ data: alertasOk });
    }
    return Promise.reject(new Error(`GET inesperado: ${url}`));
  });
}

function renderizar() {
  return render(
    <MemoryRouter>
      <DashboardUltra />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  papelAtual = "advogado";
  getMock.mockReset();
  mockGetOk();
});

afterEach(() => cleanup());

describe("DashboardUltra — Início canônico", () => {
  it("mantém marca, três sinais operacionais, Entrada Única e Radar Jurídico", async () => {
    renderizar();

    expect(
      await screen.findByRole("link", { name: "Abrir Ajuizamento" }),
    ).toBeTruthy();
    expect(
      await screen.findByRole("link", { name: "Riscos de prazos: 2" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Comunicações processuais: 2" }),
    ).toBeTruthy();
    expect(screen.getByText("Olá, Clovis.")).toBeTruthy();
    expect(screen.getByText("Marca Jurídica Configurada")).toBeTruthy();
    expect(screen.getByTestId("entrada-unica").dataset.embedded).toBe("true");
    expect(
      screen.getByRole("region", { name: "Radar Jurídico" }),
    ).toBeTruthy();

    expect(screen.queryByText("Tarefas")).toBeNull();
    expect(screen.queryByText("Movimentações")).toBeNull();
  });

  it("consulta somente o endpoint canônico de alertas com payload mínimo", async () => {
    renderizar();

    await screen.findByRole("link", { name: "Riscos de prazos: 2" });
    expect(getMock).toHaveBeenCalledWith("/atividades/alertas-inteligentes", {
      params: { limit_per_type: 1 },
    });
    expect(getMock).toHaveBeenCalledTimes(1);
  });

  it("combina intimações e movimentações na métrica de comunicações", async () => {
    renderizar();

    const comunicacoes = await screen.findByRole("link", {
      name: "Comunicações processuais: 2",
    });
    expect(comunicacoes.className).toContain("is-alerting");
    expect(screen.getByText(/2 novas · intimações e movimentações/i)).toBeTruthy();
  });

  it("destaca risco de prazo crítico e aponta para a agenda filtrada", async () => {
    renderizar();

    const prazo = await screen.findByRole("link", { name: "Riscos de prazos: 2" });
    expect(prazo.className).toContain("is-deadline");
    expect(prazo.className).toContain("is-alerting");
    expect(prazo.getAttribute("href")).toBe("/atividades?tipo=prazo");
  });

  it("mantém a Entrada Única assistida apenas para advogado+", async () => {
    papelAtual = "secretaria";
    renderizar();

    await screen.findByRole("link", { name: "Riscos de prazos: 2" });
    expect(screen.queryByTestId("entrada-unica")).toBeNull();
    expect(
      screen.getByRole("link", { name: "Abrir Entrada Única" }).getAttribute("href"),
    ).toBe("/entrada");
  });

  it("preserva sinais operacionais e bloqueia a entrada para perfil sem acesso", async () => {
    papelAtual = "cliente_externo";
    renderizar();

    expect(
      await screen.findByRole("link", { name: "Riscos de prazos: 2" }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "A Entrada Única está disponível apenas aos perfis autorizados.",
      ),
    ).toBeTruthy();
    expect(screen.queryByTestId("entrada-unica")).toBeNull();
  });

  it("degrada métricas sem inventar contagens quando alertas estão indisponíveis", async () => {
    getMock.mockRejectedValue(new Error("offline"));
    renderizar();

    await waitFor(() => {
      expect(
        screen.getByRole("link", { name: "Riscos de prazos: indisponível" }),
      ).toBeTruthy();
    });
    expect(screen.getByText("consultar agenda")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Comunicações processuais: indisponível" }),
    ).toBeTruthy();
  });
});
