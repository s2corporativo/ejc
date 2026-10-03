// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
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
import { LEGACY_REDIRECTS, STAFF_ROUTES } from "../config/moduleRegistry";

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

const integridadeOk = {
  contagens: {
    sem_responsavel: 1,
    judicial_sem_valor_causa: 2,
    sem_atualizacao_60d: 1,
  },
  total_casos_pendentes: 4,
  itens: [],
  somente_sinalizacao: true,
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
    if (url === "/atividades") return Promise.resolve({ data: atividadesOk });
    if (url === "/cases/") return Promise.resolve({ data: casosOk });
    if (url === "/cases/c9")
      return Promise.resolve({
        data: {
          id: "c9",
          titulo: "Caso que estava em andamento",
          proxima_acao: "Revisar documentos",
        },
      });
    if (url === "/documents/")
      return Promise.resolve({ data: { data: [], total: 129 } });
    if (url === "/tasks/") return Promise.resolve({ data: tarefasOk });
    if (url === "/saneamento/integridade")
      return Promise.resolve({ data: integridadeOk });
    if (url === "/legal-docs/")
      return Promise.resolve({
        data: {
          data: [
            {
              id: "p1",
              titulo: "Contestação Banco Y",
              status: "em_revisao",
              case_id: "c1",
            },
          ],
        },
      });
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

function abrirControles() {
  // Compatibilidade dos testes históricos: o dashboard agora é único e os
  // dados operacionais carregam automaticamente.
}

beforeEach(() => {
  getMock.mockReset();
  patchMock.mockReset();
  papelAtual = "advogado";
  localStorage.clear();
});

afterEach(() => {
  cleanup();
});

describe("DashboardUltra — cockpit jurídico final", () => {
  it("mantém a Entrada Única completa para carteira vazia", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/dashboard/")
        return Promise.resolve({
          data: { casos: { ativos: 0 }, clientes_ativos: 0 },
        });
      if (url === "/atividades") return Promise.resolve({ data: { data: [] } });
      if (url === "/cases/") return Promise.resolve({ data: { data: [] } });
      if (url === "/documents/")
        return Promise.resolve({ data: { data: [], total: 0 } });
      if (url === "/tasks/") return Promise.resolve({ data: { data: [] } });
      if (url === "/saneamento/integridade")
        return Promise.resolve({ data: integridadeOk });
      if (url === "/legal-docs/")
        return Promise.resolve({ data: { data: [] } });
      return Promise.reject(new Error(`GET inesperado: ${url}`));
    });

    renderizar();

    expect(screen.getByText("Leitura e análise do caso com IA")).toBeTruthy();
    expect(screen.getByTestId("entrada-unica")).toBeTruthy();
    await waitFor(() =>
      expect(screen.queryByText("Começar novo trabalho")).not.toBeTruthy(),
    );
  });

  it("compacta a entrada quando a carteira já está ativa", async () => {
    mockGetOk();
    renderizar();

    expect(await screen.findByText("Começar novo trabalho")).toBeTruthy();
    expect(
      screen
        .getByRole("link", { name: "Entrada Jurídica" })
        .getAttribute("href"),
    ).toBe("/entrada");
    expect(
      screen.getByRole("link", { name: "+ Novo Caso" }).getAttribute("href"),
    ).toBe("/entrada?modo=manual&aba=caso");
    expect(screen.queryByTestId("entrada-unica")).not.toBeTruthy();
  });

  it("mostra somente sinais operacionais reais e casos em destaque", async () => {
    mockGetOk();
    renderizar();

    await waitFor(() =>
      expect(screen.getByLabelText("Prazos hoje: 1")).toBeTruthy(),
    );
    expect(screen.getByLabelText("Clientes ativos: 48")).toBeTruthy();
    expect(screen.getByLabelText("Casos em andamento: 3")).toBeTruthy();
    expect(screen.getByLabelText("Pendências de integridade: 4")).toBeTruthy();
    expect(screen.getByText("Meus casos prioritários")).toBeTruthy();
    expect(screen.queryByText("Agenda e Prazos")).not.toBeTruthy();
    expect(screen.queryByText("Minha rotina hoje")).not.toBeTruthy();
  });

  it("prioriza a fila de decisões por revisão, prazo e risco", async () => {
    mockGetOk();
    renderizar();

    expect(
      await screen.findByText("Decisões que exigem sua atenção hoje"),
    ).toBeTruthy();
    expect(screen.getByText("Peça aguardando sua revisão")).toBeTruthy();
    expect(screen.getByText(/Contestação Banco Y/)).toBeTruthy();
    const revisar = screen.getByRole("link", { name: /Revisar peça/ });
    expect(revisar.getAttribute("href")).toBe("/casos/c1?tab=pecas#revisao");
  });

  it("oferece continuar de onde parei com dados revalidados pela API", async () => {
    localStorage.setItem("ejc_ultimo_caso_id", "c9");
    mockGetOk();
    renderizar();

    const continuar = await screen.findByRole("link", {
      name: /Continuar de onde parei: Caso que estava em andamento/,
    });
    expect(continuar.getAttribute("href")).toBe("/casos/c9");
    expect(screen.getByText("Revisar documentos")).toBeTruthy();
  });

  it("não replica a jornada do caso no dashboard", async () => {
    mockGetOk();
    renderizar();
    await screen.findByText("Meu Dia");

    expect(screen.queryByLabelText("Fluxo jurídico")).toBeNull();
    expect(screen.queryByRole("link", { name: "Provas" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Teses" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Ajuizamento" })).toBeNull();
  });

  it("restringe a Entrada Jurídica por papel", async () => {
    papelAtual = "cliente_externo";
    getMock.mockImplementation((url: string) => {
      if (url === "/dashboard/")
        return Promise.resolve({
          data: { casos: { ativos: 0 }, clientes_ativos: 0 },
        });
      if (url === "/atividades") return Promise.resolve({ data: { data: [] } });
      if (url === "/cases/") return Promise.resolve({ data: { data: [] } });
      if (url === "/documents/")
        return Promise.resolve({ data: { data: [], total: 0 } });
      if (url === "/tasks/") return Promise.resolve({ data: { data: [] } });
      if (url === "/legal-docs/")
        return Promise.resolve({ data: { data: [] } });
      return Promise.reject(new Error(`GET inesperado: ${url}`));
    });

    renderizar();

    expect(
      await screen.findByText(
        "A Entrada Única está disponível apenas aos perfis autorizados.",
      ),
    ).toBeTruthy();
    expect(screen.queryByTestId("entrada-unica")).not.toBeTruthy();
  });
});
