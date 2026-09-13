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

const getMock = vi.fn();
const postMock = vi.fn();
let papelAtual = "advogado";

vi.mock("../lib/api", () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}));

vi.mock("../stores/auth", () => ({
  useAuth: (
    selector: (state: { user: { role: string; full_name: string } }) => unknown,
  ) => selector({ user: { role: papelAtual, full_name: "Clovis Teste" } }),
}));

vi.mock("../lib/iaStatus", () => ({
  useIaStatus: () => ({ disponivel: true, mensagem: "" }),
}));

vi.mock("../lib/iaErro", () => ({
  mensagemErroIA: () => "Falha controlada da IA",
}));

import DashboardUltra from "./DashboardUltra";

const dashboardOk = {
  data: {
    casos: {
      total: 3,
      ativos: 2,
      por_status: { ativo: 2, encerrado: 1 },
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
      descricao: "Caso Alfa",
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
    {
      id: "i1",
      tipo: "intimacao",
      fonte: "djen",
      titulo: "Intimação pendente",
      date: "2099-01-04",
      status: "pendente",
    },
  ],
};

const agendaOk = {
  data: [{ id: "t1", tipo: "audiencia", hora: "09:30", local: "Fórum" }],
};

const clientesOk = {
  data: {
    data: [
      {
        id: "c1",
        nome: "Cliente Alfa",
        status: "ativo",
        email: "cliente@example.com",
      },
    ],
  },
};

const defesasOk = {
  data: {
    modalidades: [
      {
        codigo: "multa_transito",
        titulo: "Recurso de multa de trânsito",
        descricao: "Defesa prévia e recursos administrativos.",
      },
      {
        codigo: "revisao_contratual",
        titulo: "Revisão de contrato",
        descricao: "Leitura estruturada do contrato.",
      },
    ],
  },
};

function mockSucesso() {
  getMock.mockImplementation((url: string) => {
    if (url === "/dashboard/") return Promise.resolve(dashboardOk);
    if (url === "/atividades") return Promise.resolve(atividadesOk);
    if (url === "/agenda-eventos/") return Promise.resolve(agendaOk);
    if (url === "/clients/?page_size=4&status=ativo")
      return Promise.resolve(clientesOk);
    if (url === "/defesas-revisoes/meta") return Promise.resolve(defesasOk);
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
  postMock.mockReset();
  postMock.mockResolvedValue({
    data: {
      conteudo: "Resposta jurídica de teste",
      fontes_rag: ["Fonte oficial A", "Fonte oficial B"],
      alertas: ["Citação exige conferência específica"],
      aviso_hitl: "Revisão humana obrigatória",
    },
  });
  mockSucesso();
});

afterEach(() => cleanup());

describe("DashboardUltra — referência 2026", () => {
  it("aplica RBAC às ferramentas jurídicas sem esconder o estado explicativo", async () => {
    papelAtual = "advogado";
    const primeira = renderizar();
    expect(await screen.findByText("Fontes e jurisprudência")).toBeTruthy();
    expect(screen.getByText("Recurso de Multa de Trânsito")).toBeTruthy();
    primeira.unmount();

    papelAtual = "cliente_externo";
    renderizar();
    expect(
      await screen.findByText(
        "Inteligência Jurídica disponível apenas aos perfis jurídicos autorizados.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText("Fontes e jurisprudência")).toBeNull();
    expect(
      screen.getAllByText("Ferramenta restrita à equipe jurídica autorizada.")
        .length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("responde no próprio dashboard usando a porta canônica de IA", async () => {
    renderizar();

    const input = await screen.findByLabelText(
      "Pergunta rápida para a Inteligência Jurídica",
    );
    fireEvent.change(input, { target: { value: "Qual é a tese aplicável?" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith("/ia/conversar", {
        texto: "Qual é a tese aplicável?",
        area: "pesquisa_juridica",
      });
    });
    expect(await screen.findByText("Resposta jurídica de teste")).toBeTruthy();
    expect(screen.getByText("Fonte oficial A")).toBeTruthy();
    expect(screen.getByText("Fonte oficial B")).toBeTruthy();
    expect(
      screen.getByText("Atenção: Citação exige conferência específica"),
    ).toBeTruthy();
    expect(screen.getByText("Revisão humana obrigatória")).toBeTruthy();
  });

  it("bloqueia perguntas com menos de três caracteres", async () => {
    renderizar();

    const input = await screen.findByLabelText(
      "Pergunta rápida para a Inteligência Jurídica",
    );
    fireEvent.change(input, { target: { value: "oi" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });

    expect(postMock).not.toHaveBeenCalled();
    const sendButton = screen.getByRole("button", {
      name: "Enviar pergunta para a Inteligência Jurídica",
    }) as HTMLButtonElement;
    expect(sendButton.disabled).toBe(true);
  });

  it("substitui o turno anterior quando uma nova pergunta rápida é enviada", async () => {
    postMock
      .mockResolvedValueOnce({
        data: {
          conteudo: "Primeira resposta independente",
          fontes_rag: ["Fonte primeira"],
          aviso_hitl: "Revisão humana obrigatória",
        },
      })
      .mockResolvedValueOnce({
        data: {
          conteudo: "Segunda resposta independente",
          fontes_rag: ["Fonte segunda"],
          aviso_hitl: "Revisão humana obrigatória",
        },
      });

    renderizar();
    const input = await screen.findByLabelText(
      "Pergunta rápida para a Inteligência Jurídica",
    );

    fireEvent.change(input, { target: { value: "Primeira pergunta válida" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });
    expect(
      await screen.findByText("Primeira resposta independente"),
    ).toBeTruthy();

    fireEvent.change(input, { target: { value: "Segunda pergunta válida" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });

    await waitFor(() => expect(postMock).toHaveBeenCalledTimes(2));
    expect(screen.queryByText("Primeira resposta independente")).toBeNull();
    expect(
      await screen.findByText("Segunda resposta independente"),
    ).toBeTruthy();
  });

  it("exclui atividades finalizadas e usa dados reais dos novos cartões", async () => {
    renderizar();

    expect(
      (await screen.findAllByText("Tarefa pendente")).length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Tarefa concluída")).toBeNull();
    expect(screen.getByText("Cliente Alfa")).toBeTruthy();
    expect(screen.getByText("Ativo")).toBeTruthy();
  });

  it("expõe falha do dashboard em vez de inventar prazos ou carteira", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/dashboard/")
        return Promise.reject(new Error("dashboard off"));
      if (url === "/atividades") return Promise.resolve(atividadesOk);
      if (url === "/agenda-eventos/") return Promise.resolve(agendaOk);
      if (url === "/clients/?page_size=4&status=ativo")
        return Promise.resolve(clientesOk);
      if (url === "/defesas-revisoes/meta") return Promise.resolve(defesasOk);
      return Promise.reject(new Error("inesperado"));
    });

    renderizar();
    await waitFor(() => {
      expect(screen.getByText("— prazos vencidos")).toBeTruthy();
    });
    expect(screen.getByText("Dados da carteira indisponíveis.")).toBeTruthy();
  });

  it("expõe falha de atividades e não mascara a agenda como vazia", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/dashboard/") return Promise.resolve(dashboardOk);
      if (url === "/atividades")
        return Promise.reject(new Error("atividades off"));
      if (url === "/agenda-eventos/") return Promise.resolve(agendaOk);
      if (url === "/clients/?page_size=4&status=ativo")
        return Promise.resolve(clientesOk);
      if (url === "/defesas-revisoes/meta") return Promise.resolve(defesasOk);
      return Promise.reject(new Error("inesperado"));
    });

    renderizar();
    expect(
      await screen.findByText("Atividades temporariamente indisponíveis."),
    ).toBeTruthy();
    expect(
      screen.getByText("Agenda temporariamente indisponível."),
    ).toBeTruthy();
  });

  it("sinaliza degradação parcial quando somente o enriquecimento da agenda falha", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/dashboard/") return Promise.resolve(dashboardOk);
      if (url === "/atividades") return Promise.resolve(atividadesOk);
      if (url === "/agenda-eventos/")
        return Promise.reject(new Error("agenda off"));
      if (url === "/clients/?page_size=4&status=ativo")
        return Promise.resolve(clientesOk);
      if (url === "/defesas-revisoes/meta") return Promise.resolve(defesasOk);
      return Promise.reject(new Error("inesperado"));
    });

    renderizar();
    expect(
      await screen.findByText(/Horário\/local podem estar incompletos/i),
    ).toBeTruthy();
    expect(
      screen.getAllByText("Tarefa pendente").length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("mantém estado de erro de clientes isolado dos demais blocos", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/dashboard/") return Promise.resolve(dashboardOk);
      if (url === "/atividades") return Promise.resolve(atividadesOk);
      if (url === "/agenda-eventos/") return Promise.resolve(agendaOk);
      if (url === "/clients/?page_size=4&status=ativo")
        return Promise.reject(new Error("clients off"));
      if (url === "/defesas-revisoes/meta") return Promise.resolve(defesasOk);
      return Promise.reject(new Error("inesperado"));
    });

    renderizar();
    expect(
      await screen.findByText("Clientes temporariamente indisponíveis."),
    ).toBeTruthy();
  });
});
