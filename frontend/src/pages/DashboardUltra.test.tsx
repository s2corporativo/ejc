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

import DashboardUltra from "./DashboardUltra";

const dashboardOk = {
  data: {
    casos: {
      total: 3,
      ativos: 2,
      por_status: { ativo: 2, encerrado: 1 },
      por_area: [{ area: "civil", total: 3 }],
    },
    prazos: { vencidos: 1, criticos_3d: 1, proximos_7d: 2 },
    degradado: [],
  },
};

const atividadesOk = {
  data: [
    {
      id: "t1",
      tipo: "tarefa",
      fonte: "tarefa",
      titulo: "Tarefa pendente",
      date: "2099-01-02",
      status: "pendente",
    },
    {
      id: "t2",
      tipo: "tarefa",
      fonte: "tarefa",
      titulo: "Tarefa concluída",
      date: "2099-01-03",
      status: "concluida",
    },
  ],
};

const agendaOk = {
  data: [{ id: "t1", tipo: "audiencia", hora: "09:30", local: "Fórum" }],
};

const movimentosOk = {
  data: [
    {
      id: "m1",
      tipo: "despacho",
      descricao: "Juízo abriu vista para manifestação",
      case_title: "Caso Alfa",
      data_movimento: "2099-01-01T10:00:00",
    },
  ],
};

function mockSucesso() {
  getMock.mockImplementation((url: string) => {
    if (url === "/dashboard/") return Promise.resolve(dashboardOk);
    if (url === "/atividades") return Promise.resolve(atividadesOk);
    if (url === "/agenda-eventos/") return Promise.resolve(agendaOk);
    if (url === "/movimentos/recentes") return Promise.resolve(movimentosOk);
    return Promise.reject(new Error(`URL inesperada: ${url}`));
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
  mockSucesso();
});

afterEach(() => cleanup());

describe("DashboardUltra", () => {
  it("aplica RBAC aos comandos rápidos", async () => {
    papelAtual = "advogado";
    const primeira = renderizar();
    expect(await screen.findByText("Novo caso por documento")).toBeTruthy();
    expect(screen.getByText("Inteligência jurídica")).toBeTruthy();
    primeira.unmount();

    papelAtual = "cliente_externo";
    renderizar();
    await screen.findByText("Agenda e prazos");
    expect(screen.queryByText("Novo caso por documento")).toBeNull();
    expect(screen.queryByText("Importar documento")).toBeNull();
    expect(screen.queryByText("Inteligência jurídica")).toBeNull();
  });

  it("exclui tarefas finalizadas da contagem pendente e preserva descrição da movimentação", async () => {
    renderizar();

    await screen.findByText("Juízo abriu vista para manifestação");
    expect(screen.getByText("Caso Alfa")).toBeTruthy();

    const card = screen.getByText("Tarefas pendentes").closest("a");
    expect(card?.textContent).toContain("1");
    expect(screen.getByText("SNAPSHOT")).toBeTruthy();
  });

  it("expõe falha do dashboard em vez de inventar indicadores", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/dashboard/")
        return Promise.reject(new Error("dashboard off"));
      if (url === "/atividades") return Promise.resolve(atividadesOk);
      if (url === "/agenda-eventos/") return Promise.resolve(agendaOk);
      if (url === "/movimentos/recentes") return Promise.resolve(movimentosOk);
      return Promise.reject(new Error("inesperado"));
    });

    renderizar();
    await waitFor(() => {
      expect(
        screen.getAllByText("Fonte indisponível").length,
      ).toBeGreaterThanOrEqual(2);
    });
    expect(screen.getByText("Prazos indisponíveis")).toBeTruthy();
  });

  it("expõe falha de atividades e não mascara a agenda como vazia", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/dashboard/") return Promise.resolve(dashboardOk);
      if (url === "/atividades")
        return Promise.reject(new Error("atividades off"));
      if (url === "/agenda-eventos/") return Promise.resolve(agendaOk);
      if (url === "/movimentos/recentes") return Promise.resolve(movimentosOk);
      return Promise.reject(new Error("inesperado"));
    });

    renderizar();
    expect(await screen.findByText("Agenda indisponível no momento.")).toBeTruthy();
    const card = screen.getByText("Tarefas pendentes").closest("a");
    expect(card?.textContent).toContain("Fonte indisponível");
  });

  it("sinaliza degradação parcial quando somente o enriquecimento da agenda falha", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/dashboard/") return Promise.resolve(dashboardOk);
      if (url === "/atividades") return Promise.resolve(atividadesOk);
      if (url === "/agenda-eventos/")
        return Promise.reject(new Error("agenda off"));
      if (url === "/movimentos/recentes") return Promise.resolve(movimentosOk);
      return Promise.reject(new Error("inesperado"));
    });

    renderizar();
    expect(
      await screen.findByText(
        /Horário, local e subtipo dos compromissos podem estar indisponíveis/i,
      ),
    ).toBeTruthy();
    expect(screen.getByText("Tarefa pendente")).toBeTruthy();
  });

  it("expõe falha de movimentações", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/dashboard/") return Promise.resolve(dashboardOk);
      if (url === "/atividades") return Promise.resolve(atividadesOk);
      if (url === "/agenda-eventos/") return Promise.resolve(agendaOk);
      if (url === "/movimentos/recentes")
        return Promise.reject(new Error("mov off"));
      return Promise.reject(new Error("inesperado"));
    });

    renderizar();
    expect(await screen.findByText("Movimentações indisponíveis.")).toBeTruthy();
  });
});
