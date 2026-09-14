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
const patchMock = vi.fn();
let papelAtual = "advogado";

vi.mock("../lib/api", () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    patch: (...args: unknown[]) => patchMock(...args),
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

const alertasOk = {
  resumo: {
    prazo: { ativos: 2, novos: 1, criticos: 1, altos: 1 },
    tarefa: { ativos: 1, novos: 1, criticos: 0, altos: 1 },
    intimacao: { ativos: 1, novos: 1, criticos: 0, altos: 1 },
    movimentacao: { ativos: 1, novos: 1, criticos: 0, altos: 1 },
  },
  itens: {
    prazo: [
      {
        source_type: "prazo",
        source_id: "p1",
        titulo: "Prazo contestação",
        descricao: "Apresentar contestação",
        data: "2026-09-14",
        case_id: "c1",
        caso_titulo: "Caso Alfa",
        responsavel_nome: "Dra. Ana",
        nivel_alerta: "critico",
        estado_alerta: "novo",
        link: "/atividades?tipo=prazo&caso=c1",
      },
    ],
    tarefa: [
      {
        source_type: "tarefa",
        source_id: "t1",
        titulo: "Revisar minuta",
        data: "2026-09-14",
        case_id: "c1",
        caso_titulo: "Caso Alfa",
        responsavel_nome: "Dr. Bruno",
        nivel_alerta: "alto",
        estado_alerta: "novo",
        link: "/atividades?tipo=tarefa&caso=c1",
      },
    ],
    intimacao: [
      {
        source_type: "intimacao",
        source_id: "i1",
        titulo: "Intimação DJEN",
        data: "2026-09-13",
        case_id: "c1",
        caso_titulo: "Caso Alfa",
        responsavel_nome: "Dra. Ana",
        nivel_alerta: "alto",
        estado_alerta: "novo",
        link: "/atividades?tipo=intimacao&caso=c1",
      },
    ],
    movimentacao: [
      {
        source_type: "movimentacao",
        source_id: "m1",
        titulo: "Movimentação: Caso Alfa",
        descricao: "Decisão interlocutória publicada",
        data: "2026-09-13T10:00:00-03:00",
        case_id: "c1",
        caso_titulo: "Caso Alfa",
        responsavel_nome: "Dra. Ana",
        nivel_alerta: "alto",
        estado_alerta: "novo",
        link: "/casos/c1",
      },
    ],
  },
};

function mockGetOk() {
  getMock.mockImplementation((url: string) => {
    if (url === "/atividades/alertas-inteligentes")
      return Promise.resolve({ data: alertasOk });
    return Promise.reject(new Error(`GET inesperado: ${url}`));
  });
}

function mockPostOk() {
  postMock.mockImplementation((url: string, payload?: any) => {
    if (url === "/sala-juridica")
      return Promise.resolve({ data: { id: "sess-dashboard-1" } });
    if (url === "/sala-juridica/sess-dashboard-1/mensagens")
      return Promise.resolve({
        data: {
          mensagem_ia: {
            id: "msg-ia-1",
            conteudo: "Resposta jurídica de teste",
            fontes: [{ titulo: "Fonte oficial A" }],
            alertas: ["Citação exige conferência específica"],
          },
          aviso_hitl: "Revisão humana obrigatória",
          indicadores_confianca: {
            fontes_rastreaveis: 2,
            documentos_utilizados: 1,
            fatos_nao_confirmados: 3,
            citacoes_a_conferir: 1,
            revisao_humana_necessaria: true,
          },
          proxima_acao_sugerida: {
            acao: "Obter o contrato original",
            prioridade: "alta",
            justificativa: "Documento necessário para confirmar a tese.",
          },
        },
      });
    if (url === "/sala-juridica/sess-dashboard-1/anexos")
      return Promise.resolve({
        data: {
          anexados: [{ id: "anexo-1", nome_original: "processo.pdf" }],
          erros: [],
        },
      });
    if (url === "/sala-juridica/sess-dashboard-1/proxima-acao/confirmar") {
      expect(payload).toEqual({ acao: "Obter o contrato original" });
      return Promise.resolve({ data: { confirmada: true, versao: 4 } });
    }
    return Promise.reject(new Error(`POST inesperado: ${url}`));
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
  patchMock.mockReset();
  patchMock.mockResolvedValue({ data: { estado: "visualizado" } });
  mockGetOk();
  mockPostOk();
});

afterEach(() => cleanup());

describe("DashboardUltra — cockpit IA + alertas inteligentes", () => {
  it("mantém marca evidente, contatos, IA principal e radar jurídico horizontal", async () => {
    renderizar();
    expect(
      await screen.findByAltText("De Paula Teixeira Advogados"),
    ).toBeTruthy();
    expect(
      screen.getByTitle("WhatsApp institucional não configurado"),
    ).toBeTruthy();
    expect(
      screen.queryByRole("link", { name: "Abrir WhatsApp do escritório" }),
    ).toBeNull();
    expect(
      screen.queryByRole("link", { name: "Enviar e-mail ao escritório" }),
    ).toBeNull();
    expect(
      screen.getByLabelText("Pergunta rápida para a Inteligência Jurídica"),
    ).toBeTruthy();
    expect(screen.getByLabelText("Radar Jurídico")).toBeTruthy();
  });

  it("carrega apenas o endpoint canônico de alertas inteligentes", async () => {
    renderizar();
    expect(await screen.findByLabelText(/Prazos: 2\. 1 novos/i)).toBeTruthy();
    expect(getMock).toHaveBeenCalledWith("/atividades/alertas-inteligentes", {
      params: { limit_per_type: 5 },
    });
    expect(getMock).toHaveBeenCalledTimes(1);
  });

  it("abre detalhes acionáveis com responsável, urgência e estado", async () => {
    renderizar();
    const sinal = await screen.findByRole("button", { name: /Prazos: 2/i });
    expect(sinal.className).toContain("is-alerting");
    fireEvent.click(sinal);
    expect(await screen.findByText("Prazo contestação")).toBeTruthy();
    expect(screen.getByText(/Responsável: Dra\. Ana/)).toBeTruthy();
    expect(screen.getByText("Crítico")).toBeTruthy();
    expect(screen.getByText("Novo")).toBeTruthy();
  });

  it("marca como visualizado sem concluir a atividade de origem", async () => {
    renderizar();
    fireEvent.click(await screen.findByRole("button", { name: /Prazos: 2/i }));
    fireEvent.click(await screen.findByRole("button", { name: "Visto" }));
    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith("/atividades/alertas/prazo/p1", {
        estado: "visualizado",
      });
    });
  });

  it("trata somente o alerta e recarrega o cockpit", async () => {
    renderizar();
    fireEvent.click(await screen.findByRole("button", { name: /Tarefas: 1/i }));
    fireEvent.click(
      await screen.findByRole("button", { name: /Tratar alerta/i }),
    );
    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith("/atividades/alertas/tarefa/t1", {
        estado: "tratado",
      });
      expect(getMock.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("mantém os quatro alertas com cores/classes distintas", async () => {
    renderizar();
    expect(
      (await screen.findByRole("button", { name: /Prazos: 2/i })).className,
    ).toContain("is-deadline");
    expect(
      screen.getByRole("button", { name: /Tarefas: 1/i }).className,
    ).toContain("is-task");
    expect(
      screen.getByRole("button", { name: /Intimações: 1/i }).className,
    ).toContain("is-intimation");
    expect(
      screen.getByRole("button", { name: /Movimentações: 1/i }).className,
    ).toContain("is-movement");
  });

  it("aplica RBAC à IA sem esconder os alertas operacionais", async () => {
    papelAtual = "cliente_externo";
    renderizar();
    expect(
      await screen.findByRole("button", { name: /Prazos: 2/i }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Inteligência Jurídica disponível apenas aos perfis jurídicos autorizados.",
      ),
    ).toBeTruthy();
  });

  it("envia modo jurídico selecionado e Contexto EJC somente quando opt-in", async () => {
    renderizar();
    await screen.findByRole("button", { name: "Estratégia" });
    fireEvent.click(screen.getByRole("button", { name: "Estratégia" }));
    fireEvent.click(screen.getByRole("button", { name: /Contexto EJC/i }));
    const input = screen.getByLabelText(
      "Pergunta rápida para a Inteligência Jurídica",
    );
    fireEvent.change(input, {
      target: { value: "Quais casos precisam da minha atenção hoje?" },
    });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });
    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith(
        "/sala-juridica/sess-dashboard-1/mensagens",
        expect.objectContaining({
          modo: "estrategia_da_parte",
          incluir_contexto_ejc: true,
          usar_rag: true,
        }),
      );
    });
  });

  it("exibe indicadores objetivos e próxima ação sem percentual artificial", async () => {
    renderizar();
    const input = await screen.findByLabelText(
      "Pergunta rápida para a Inteligência Jurídica",
    );
    fireEvent.change(input, {
      target: { value: "Analise este caso de teste" },
    });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });
    expect(await screen.findByText("Resposta jurídica de teste")).toBeTruthy();
    expect(screen.getByText("Fontes rastreáveis: 2")).toBeTruthy();
    expect(screen.getByText("Documentos usados: 1")).toBeTruthy();
    expect(screen.getByText("Fatos não confirmados: 3")).toBeTruthy();
    expect(screen.getByText("Citações a conferir: 1")).toBeTruthy();
    expect(screen.getByText("Obter o contrato original")).toBeTruthy();
    expect(screen.queryByText(/% de confiança/i)).toBeNull();
  });

  it("confirma a próxima ação no dossiê sem criar tarefa ou prazo", async () => {
    renderizar();
    const input = await screen.findByLabelText(
      "Pergunta rápida para a Inteligência Jurídica",
    );
    fireEvent.change(input, {
      target: { value: "Analise este caso de teste" },
    });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });
    const confirmar = await screen.findByRole("button", {
      name: "Confirmar ação",
    });
    fireEvent.click(confirmar);
    expect(await screen.findByText(/Confirmada no dossiê/i)).toBeTruthy();
    expect(postMock).toHaveBeenCalledWith(
      "/sala-juridica/sess-dashboard-1/proxima-acao/confirmar",
      { acao: "Obter o contrato original" },
    );
  });

  it("anexo muda para modo documental e preserva a mesma sessão", async () => {
    const { container } = renderizar();
    await screen.findByLabelText(
      "Pergunta rápida para a Inteligência Jurídica",
    );
    const fileInput = container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const file = new File(["conteúdo sintético"], "processo.pdf", {
      type: "application/pdf",
    });
    fireEvent.change(fileInput, { target: { files: [file] } });
    expect(await screen.findByText(/processo\.pdf/)).toBeTruthy();
    expect(
      screen
        .getByRole("button", { name: "Documentos" })
        .getAttribute("aria-pressed"),
    ).toBe("true");
    expect(postMock).toHaveBeenCalledWith(
      "/sala-juridica/sess-dashboard-1/anexos",
      expect.any(FormData),
      { headers: { "Content-Type": "multipart/form-data" } },
    );
  });

  it("degrada alertas sem inventar contagens", async () => {
    getMock.mockRejectedValue(new Error("offline"));
    renderizar();
    expect(
      await screen.findByRole("button", { name: /Prazos: —/i }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Prazos: —/i }));
    expect(
      await screen.findByText("Alertas temporariamente indisponíveis."),
    ).toBeTruthy();
  });
});
