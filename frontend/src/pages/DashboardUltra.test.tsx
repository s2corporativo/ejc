// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { addDays, format } from "date-fns";

const getMock = vi.fn();
const patchMock = vi.fn();
let papelAtual = "advogado";

vi.mock("../lib/api", () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    patch: (...args: unknown[]) => patchMock(...args),
  },
}));

vi.mock("../components/Toast", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock("../stores/auth", () => ({
  useAuth: (
    selector: (state: { user: { role: string; full_name: string } }) => unknown,
  ) => selector({ user: { role: papelAtual, full_name: "Clovis Teste" } }),
}));

vi.mock("./EntradaUnica", () => ({
  EntradaInteligente: ({ embedded }: { embedded?: boolean }) => (
    <div data-testid="entrada-unica" data-embedded={String(Boolean(embedded))}>
      Entrada Única embutida
    </div>
  ),
}));

import DashboardUltra from "./DashboardUltra";

const dataBase = new Date();
const hoje = format(dataBase, "yyyy-MM-dd");
const amanha = format(addDays(dataBase, 1), "yyyy-MM-dd");
const futuro = format(addDays(dataBase, 5), "yyyy-MM-dd");

const kpisOk = {
  casos: { ativos: 3, total: 9 },
  clientes_ativos: 48,
  prazos: { vencidos: 0, criticos_3d: 2, proximos_7d: 5 },
};

const atividadesOk = {
  data: [
    {
      id: "a1",
      tipo: "prazo",
      titulo: "Prazo final — Contestação",
      date: `${hoje}T11:30:00`,
      dias_restantes: 0,
      urgencia: "critico",
      case_id: "c1",
      caso_titulo: "Empresa X vs. Banco Y",
    },
    {
      id: "a2",
      tipo: "tarefa",
      titulo: "Revisão de teses",
      date: `${hoje}T17:30:00`,
      dias_restantes: 0,
      urgencia: "normal",
      caso_titulo: null,
    },
    {
      id: "a3",
      tipo: "intimacao",
      titulo: "Intimação — audiência",
      date: `${amanha}T09:00:00`,
      dias_restantes: 1,
      urgencia: "atencao",
      case_id: "c2",
      caso_titulo: "João Silva vs. Plano de Saúde",
    },
  ],
};

const casosOk = {
  data: [
    {
      id: "c1",
      titulo: "Empresa X vs. Banco Y",
      status: "aberto",
      area: "civel",
      prioridade: "alta",
      risco: "alto",
      proxima_acao: "Protocolar contestação",
      proxima_acao_prazo: `${hoje}T18:00:00`,
      numero_processo: "1001234-56.2023.8.26.0100",
    },
    {
      id: "c2",
      titulo: "João Silva vs. Plano de Saúde",
      status: "encerrado",
      area: "saude",
      prioridade: "baixa",
      proxima_acao: "Arquivar comprovantes",
      numero_processo: null,
      numero_interno: "DPT-2026-0042",
    },
  ],
  total: 10,
  page: 1,
  page_size: 4,
};

const tarefasOk = {
  data: [
    {
      id: "t1",
      titulo: "Revisar petição inicial",
      status: "a_fazer",
      prioridade: "alta",
      data_limite: hoje,
    },
    {
      id: "t2",
      titulo: "Retorno para cliente — Grupo Santos",
      status: "a_fazer",
      data_limite: null,
    },
    {
      id: "t3",
      titulo: "Estudo tema 1.234/STJ",
      status: "concluida",
      data_limite: hoje,
      concluida_em: `${hoje}T08:00:00`,
    },
    {
      id: "t4",
      titulo: "Tarefa futura que não pertence à rotina de hoje",
      status: "a_fazer",
      data_limite: futuro,
    },
  ],
};

function mockGetOk() {
  getMock.mockImplementation((url: string) => {
    if (url === "/dashboard/") return Promise.resolve({ data: kpisOk });
    if (url === "/atividades")
      return Promise.resolve({ data: atividadesOk });
    if (url === "/cases/") return Promise.resolve({ data: casosOk });
    if (url === "/documents/") return Promise.resolve({ data: { data: [], total: 129 } });
    if (url === "/tasks/") return Promise.resolve({ data: tarefasOk });
    return Promise.reject(new Error(`GET inesperado: ${url}`));
  });
}

function renderizar(rota = "/") {
  return render(
    <MemoryRouter initialEntries={[rota]}>
      <DashboardUltra />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  getMock.mockReset();
  patchMock.mockReset();
  papelAtual = "advogado";
});

afterEach(() => {
  cleanup();
});

describe("DashboardUltra — identidade premium DPT", () => {
  it("abre na IA como padrão e não carrega o painel operacional", () => {
    mockGetOk();
    renderizar();

    const abaIa = screen.getByRole("tab", { name: /IA/ });
    const painelIa = document.getElementById("ejc-dashboard-ia");
    const painelControles = document.getElementById("ejc-dashboard-controles");

    expect(abaIa.getAttribute("aria-selected")).toBe("true");
    expect(abaIa.tabIndex).toBe(0);
    expect(painelIa?.hasAttribute("hidden")).toBe(false);
    expect(painelControles?.hasAttribute("hidden")).toBe(true);
    expect(screen.getByTestId("entrada-unica").getAttribute("data-embedded")).toBe(
      "true",
    );
    expect(getMock).not.toHaveBeenCalled();
  });

  it("carrega os controles sem desmontar a Entrada Única", async () => {
    mockGetOk();
    renderizar();
    const entradaAntes = screen.getByTestId("entrada-unica");

    fireEvent.click(screen.getByRole("tab", { name: /Controles/ }));

    expect(await screen.findByText("Agenda e Prazos")).toBeTruthy();
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(5));
    expect(document.getElementById("ejc-dashboard-ia")?.hasAttribute("hidden")).toBe(
      true,
    );
    expect(
      document.getElementById("ejc-dashboard-controles")?.hasAttribute("hidden"),
    ).toBe(false);
    expect(screen.getByTestId("entrada-unica")).toBe(entradaAntes);

    fireEvent.click(screen.getByRole("tab", { name: /IA/ }));
    expect(screen.getByTestId("entrada-unica")).toBe(entradaAntes);
  });

  it("permite navegar entre IA e Controles pelo teclado", () => {
    mockGetOk();
    renderizar();

    const abaIa = screen.getByRole("tab", { name: /IA/ });
    const abaControles = screen.getByRole("tab", { name: /Controles/ });
    abaIa.focus();

    fireEvent.keyDown(abaIa, { key: "ArrowRight" });
    expect(abaControles.getAttribute("aria-selected")).toBe("true");
    expect(abaControles.tabIndex).toBe(0);
    expect(document.activeElement).toBe(abaControles);

    fireEvent.keyDown(abaControles, { key: "Home" });
    expect(abaIa.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(abaIa);
  });

  it("sauda o usuário pelo primeiro nome e compõe a referência", async () => {
    mockGetOk();
    renderizar("/?modo=controles");

    expect(
      await screen.findByText(/, Clovis!/),
    ).toBeTruthy();
    expect(screen.getByText("Disciplina hoje. Grandes conquistas sempre.")).toBeTruthy();
    expect(document.getElementById("ejc-dashboard-ia")?.hasAttribute("hidden")).toBe(
      true,
    );
    expect(screen.getByText("Agenda e Prazos")).toBeTruthy();
    expect(screen.getByText("Casos em destaque")).toBeTruthy();
    expect(screen.getByText("Acesso rápido")).toBeTruthy();
    expect(screen.getByText("Minha rotina hoje")).toBeTruthy();
  });

  it("exibe sinais operacionais com números reais dos endpoints", async () => {
    mockGetOk();
    renderizar("/?modo=controles");

    // Prazos hoje = atividades tipo prazo com dias_restantes 0 → 1
    await waitFor(() =>
      expect(screen.getByLabelText("Prazos hoje: 1")).toBeTruthy(),
    );
    expect(screen.getByLabelText("Clientes ativos: 48")).toBeTruthy();
    expect(screen.getByLabelText("Casos em andamento: 3")).toBeTruthy();
    expect(
      screen.getByLabelText("Documentos recentes: 129"),
    ).toBeTruthy();
  });

  it("filtra a agenda por aba Hoje/Amanhã/Esta semana", async () => {
    mockGetOk();
    renderizar("/?modo=controles");

    expect(await screen.findByText("Prazo final — Contestação")).toBeTruthy();
    expect(screen.queryByText("Intimação — audiência")).not.toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "Amanhã" }));
    expect(screen.getByText("Intimação — audiência")).toBeTruthy();
    expect(screen.queryByText("Prazo final — Contestação")).not.toBeTruthy();
  });

  it("prioriza casos em destaque por risco, prazo e próxima ação", async () => {
    mockGetOk();
    renderizar("/?modo=controles");

    expect(
      (await screen.findAllByText("Empresa X vs. Banco Y")).length,
    ).toBeGreaterThan(0);
    const chips = screen.getAllByText("Em andamento");
    expect(chips.length).toBeGreaterThan(0);
    expect(screen.getByText("Concluso")).toBeTruthy();
    expect(screen.getByText(/Proc. nº 1001234-56\.2023\.8\.26\.0100/)).toBeTruthy();
    expect(screen.getByText(/Próxima: Protocolar contestação/)).toBeTruthy();
  });

  it("filtra a agenda pelo dia selecionado no calendário", async () => {
    mockGetOk();
    renderizar("/?modo=controles");

    const hojeLabel = format(dataBase, "dd/MM/yyyy");
    const botaoDia = await screen.findByRole("button", { name: hojeLabel });
    fireEvent.click(botaoDia);

    expect(screen.getByRole("button", { name: "Remover filtro de data" })).toBeTruthy();
    expect(screen.getByText("Prazo final — Contestação")).toBeTruthy();
    expect(screen.queryByText("Intimação — audiência")).not.toBeTruthy();
  });

  it("mostra na rotina apenas tarefas acionáveis hoje e conclusões do dia", async () => {
    mockGetOk();
    renderizar("/?modo=controles");

    expect(await screen.findByText("Revisar petição inicial")).toBeTruthy();
    expect(screen.getByText("Retorno para cliente — Grupo Santos")).toBeTruthy();
    expect(screen.getByText("Estudo tema 1.234/STJ")).toBeTruthy();
    expect(
      screen.queryByText("Tarefa futura que não pertence à rotina de hoje"),
    ).not.toBeTruthy();
    expect(screen.getByText("1 de 3 concluídas")).toBeTruthy();
  });

  it("conclui tarefa da rotina via PATCH e reage ao clique", async () => {
    mockGetOk();
    patchMock.mockResolvedValue({ data: {} });
    renderizar("/?modo=controles");

    const botao = await screen.findByRole("button", {
      name: /Revisar petição inicial/,
    });
    fireEvent.click(botao);

    await waitFor(() =>
      expect(patchMock).toHaveBeenCalledWith("/tasks/t1", {
        status: "concluida",
      }),
    );
  });

  it("reabre tarefa concluída com status canônico a_fazer", async () => {
    mockGetOk();
    patchMock.mockResolvedValue({ data: {} });
    renderizar("/?modo=controles");

    const botao = await screen.findByRole("button", {
      name: /Estudo tema 1\.234\/STJ/,
    });
    fireEvent.click(botao);

    await waitFor(() =>
      expect(patchMock).toHaveBeenCalledWith("/tasks/t3", {
        status: "a_fazer",
      }),
    );
  });

  it("degrada para traço quando a fonte falha (nunca zero falso)", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/atividades")
        return Promise.reject(new Error("fora do ar"));
      if (url === "/dashboard/")
        return Promise.reject(new Error("fora do ar"));
      if (url === "/cases/") return Promise.resolve({ data: casosOk });
      if (url === "/documents/")
        return Promise.resolve({ data: { data: [], total: 129 } });
      if (url === "/tasks/") return Promise.resolve({ data: tarefasOk });
      return Promise.reject(new Error(`GET inesperado: ${url}`));
    });
    renderizar("/?modo=controles");

    await waitFor(() =>
      expect(screen.getByLabelText("Prazos hoje: —")).toBeTruthy(),
    );
    expect(screen.getByLabelText("Clientes ativos: —")).toBeTruthy();
    expect(screen.getByText("Agenda indisponível agora.")).toBeTruthy();
  });

  it("restringe a Entrada Única por papel (perfis autorizados)", async () => {
    mockGetOk();
    papelAtual = "cliente_externo";
    renderizar();

    expect(
      await screen.findByText(
        "A Entrada Única está disponível apenas aos perfis autorizados.",
      ),
    ).toBeTruthy();
    expect(screen.queryByTestId("entrada-unica")).not.toBeTruthy();
    expect(getMock).not.toHaveBeenCalled();
  });
});
