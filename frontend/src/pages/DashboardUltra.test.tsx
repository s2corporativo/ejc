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
    prazos: { vencidos: 1, criticos_3d: 2, proximos_7d: 4 },
    degradado: [],
  },
};

const atividadesOk = {
  data: [
    {
      id: "t1",
      tipo: "tarefa",
      titulo: "Tarefa pendente",
      status: "pendente",
    },
    {
      id: "t2",
      tipo: "tarefa",
      titulo: "Tarefa concluída",
      status: "concluida",
    },
    {
      id: "i1",
      tipo: "intimacao",
      fonte: "djen",
      titulo: "Intimação pendente",
      status: "pendente",
    },
    {
      id: "m1",
      tipo: "movimentacao",
      fonte: "datajud",
      titulo: "Movimentação nova",
      status: "pendente",
    },
  ],
};

function mockSucesso() {
  getMock.mockImplementation((url: string) => {
    if (url === "/dashboard/") return Promise.resolve(dashboardOk);
    if (url === "/atividades") return Promise.resolve(atividadesOk);
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
  postMock.mockImplementation((url: string) => {
    if (url === "/sala-juridica") {
      return Promise.resolve({ data: { id: "sess-dashboard-1" } });
    }
    if (url === "/sala-juridica/sess-dashboard-1/mensagens") {
      return Promise.resolve({
        data: {
          mensagem_ia: {
            id: "msg-ia-1",
            conteudo: "Resposta jurídica de teste",
            fontes: [{ titulo: "Fonte oficial A" }],
            alertas: ["Citação exige conferência específica"],
          },
          aviso_hitl: "Revisão humana obrigatória",
        },
      });
    }
    if (url === "/sala-juridica/sess-dashboard-1/anexos") {
      return Promise.resolve({
        data: {
          anexados: [{ id: "anexo-1", nome_original: "processo.pdf" }],
          erros: [],
        },
      });
    }
    return Promise.reject(new Error(`POST inesperado: ${url}`));
  });
  mockSucesso();
});

afterEach(() => cleanup());

describe("DashboardUltra — cockpit IA-first", () => {
  it("mantém a marca evidente, IA como área principal e radar jurídico horizontal", async () => {
    renderizar();
    expect(
      await screen.findByAltText("De Paula Teixeira Advogados"),
    ).toBeTruthy();
    expect(
      screen.getByText(/Converse, anexe, analise e transforme informação/i),
    ).toBeTruthy();
    expect(
      screen.getByLabelText("Pergunta rápida para a Inteligência Jurídica"),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Abrir WhatsApp do escritório" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Enviar e-mail ao escritório" }),
    ).toBeTruthy();
    expect(screen.getByText("Radar Jurídico")).toBeTruthy();
    expect(
      screen.getByRole("link", {
        name: /ACP sindical: honorários sucumbenciais contra a União/i,
      }),
    ).toBeTruthy();
  });

  it("carrega somente os dados necessários para IA e radar operacional", async () => {
    renderizar();
    await screen.findByLabelText(/Prazos: 3\. 1 vencidos · 2 críticos/i);
    expect(getMock).toHaveBeenCalledWith("/dashboard/");
    expect(getMock).toHaveBeenCalledWith("/atividades", {
      params: { apenas_pendentes: false },
    });
    expect(getMock).toHaveBeenCalledTimes(2);
  });

  it("mostra sinais distintos para prazo, tarefa e intimação", async () => {
    renderizar();
    expect(
      await screen.findByLabelText(/Prazos: 3\. 1 vencidos · 2 críticos/i),
    ).toBeTruthy();
    expect(screen.getByLabelText(/Tarefas: 1\. pendentes/i)).toBeTruthy();
    expect(screen.getByLabelText(/Intimações: 1\. a tratar/i)).toBeTruthy();
  });

  it("aplica RBAC à IA sem esconder o radar operacional", async () => {
    papelAtual = "cliente_externo";
    renderizar();
    expect(
      await screen.findByText(
        "Inteligência Jurídica disponível apenas aos perfis jurídicos autorizados.",
      ),
    ).toBeTruthy();
    expect(
      screen.getByLabelText(/Prazos: 3\. 1 vencidos · 2 críticos/i),
    ).toBeTruthy();
  });

  it("responde no próprio dashboard usando a sessão canônica da Sala Jurídica", async () => {
    renderizar();
    const input = await screen.findByLabelText(
      "Pergunta rápida para a Inteligência Jurídica",
    );
    fireEvent.change(input, { target: { value: "Qual é a tese aplicável?" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith("/sala-juridica", {
        titulo: "Qual é a tese aplicável?",
      });
      expect(postMock).toHaveBeenCalledWith(
        "/sala-juridica/sess-dashboard-1/mensagens",
        {
          conteudo: "Qual é a tese aplicável?",
          modo: "conversa_livre",
          incluir_workspace: true,
          usar_rag: true,
        },
      );
    });
    expect(await screen.findByText("Resposta jurídica de teste")).toBeTruthy();
    expect(screen.getByText("Fonte oficial A")).toBeTruthy();
    expect(screen.getByText("Revisão humana obrigatória")).toBeTruthy();
  });

  it("mantém histórico e usa a mesma sessão conversacional", async () => {
    let mensagens = 0;
    postMock.mockImplementation((url: string) => {
      if (url === "/sala-juridica")
        return Promise.resolve({ data: { id: "sess-dashboard-1" } });
      if (url === "/sala-juridica/sess-dashboard-1/mensagens") {
        mensagens += 1;
        return Promise.resolve({
          data: {
            mensagem_ia: {
              id: `ia-${mensagens}`,
              conteudo:
                mensagens === 1 ? "Primeira resposta" : "Segunda resposta",
              fontes: [],
              alertas: [],
            },
            aviso_hitl: "Revisão humana obrigatória",
          },
        });
      }
      return Promise.reject(new Error(`POST inesperado: ${url}`));
    });

    renderizar();
    const input = await screen.findByLabelText(
      "Pergunta rápida para a Inteligência Jurídica",
    );
    fireEvent.change(input, { target: { value: "Primeira pergunta válida" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(await screen.findByText("Primeira resposta")).toBeTruthy();
    fireEvent.change(input, { target: { value: "Segunda pergunta válida" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(await screen.findByText("Segunda resposta")).toBeTruthy();
    expect(screen.getByText("Primeira resposta")).toBeTruthy();
    expect(postMock).toHaveBeenCalledTimes(3);
  });

  it("anexa documento à mesma sessão antes da análise", async () => {
    const { container } = renderizar();
    await screen.findByLabelText(
      "Pergunta rápida para a Inteligência Jurídica",
    );
    const inputFile = container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const file = new File(["conteúdo jurídico sintético"], "processo.pdf", {
      type: "application/pdf",
    });
    fireEvent.change(inputFile, { target: { files: [file] } });

    expect(await screen.findByText(/processo\.pdf/)).toBeTruthy();
    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith(
        "/sala-juridica/sess-dashboard-1/anexos",
        expect.any(FormData),
        { headers: { "Content-Type": "multipart/form-data" } },
      );
    });
  });

  it("degrada prazos e atividades sem inventar contagens", async () => {
    getMock.mockRejectedValue(new Error("offline"));
    renderizar();
    expect(await screen.findByLabelText(/Prazos: —/i)).toBeTruthy();
    expect(screen.getByLabelText(/Tarefas: —/i)).toBeTruthy();
    expect(screen.getByLabelText(/Intimações: —/i)).toBeTruthy();
  });
});
