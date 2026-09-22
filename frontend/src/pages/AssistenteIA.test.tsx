// @vitest-environment jsdom
// Assistente IA sobre as PORTAS CANÔNICAS por capacidade (item I1).
// O que quebraria em silêncio se ninguém travasse:
//   • a tela voltar a chamar /ai/pesquisar, /ai/resumir-texto, /ai/gerar-minuta
//     ou /ia-especializada/{perfil} — cada porta com qualidade própria;
//   • o aviso de HITL sumir da tela (rascunho apresentado como resposta final);
//   • as fontes do RAG deixarem de aparecer (advogado conferindo o que não vê);
//   • o limite de caracteres existir só no backend: a pessoa escreve a peça
//     inteira e leva 422 no fim (achado E6).
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";

const postMock = vi.fn();
const getMock = vi.fn();

vi.mock("../lib/api", () => ({
  default: { post: (...a: unknown[]) => postMock(...a), get: (...a: unknown[]) => getMock(...a) },
  getAccessToken: () => null,
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

vi.mock("../lib/iaStatus", () => ({
  MENSAGEM_IA_NAO_ATIVADA: "IA não ativada.",
  useIaStatus: () => ({ disponivel: true, mensagem: null }),
}));

import AssistenteIA from "./AssistenteIA";

const RESPOSTA_CANONICA = {
  conteudo: "Rascunho da análise jurídica.",
  capacidade: "conversar",
  tarefa: "pesquisa_juridica",
  modelo: "anthropic/claude",
  provider: "anthropic",
  log_id: "log-1",
  is_rascunho: true,
  requer_revisao: true,
  status_hitl: "gerado",
  aviso_hitl: "Rascunho sujeito à revisão humana (HITL obrigatório — OAB).",
  fontes_rag: [{ titulo: "Precedente interno 123", categoria: "precedente" }],
  citacoes: [],
  alertas: ["Citação não confirmada na base."],
  custo_estimado_brl: 0.1,
  tokens: { input: 10, output: 5, total: 15 },
};

function montar() {
  return render(
    <MemoryRouter>
      <AssistenteIA />
    </MemoryRouter>,
  );
}

function trocarPara(rotulo: string) {
  // Padrao vem do catalogo estatico de modulos e ja tem os metacaracteres
  // escapados; nao ha entrada de usuario. Ver docs/seguranca/SAST_BASELINE.md
  // nosemgrep: javascript.lang.security.audit.detect-non-literal-regexp.detect-non-literal-regexp
  fireEvent.click(screen.getByRole("button", { name: new RegExp(rotulo) }));
}

afterEach(() => {
  cleanup();
  postMock.mockReset();
  getMock.mockReset();
});

describe("AssistenteIA — portas canônicas", () => {
  it("pesquisa chama /ia/conversar", async () => {
    postMock.mockResolvedValue({ data: RESPOSTA_CANONICA });
    montar();
    fireEvent.change(screen.getByPlaceholderText("Sua pergunta jurídica…"), {
      target: { value: "Cabe dano moral por negativação indevida?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Executar/ }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][0]).toBe("/ia/conversar");
  });

  it("envia provider auto por padrão e permite solicitar Claude explicitamente", async () => {
    postMock.mockResolvedValue({ data: RESPOSTA_CANONICA });
    montar();
    fireEvent.change(screen.getByPlaceholderText("Sua pergunta jurídica…"), {
      target: { value: "Analise esta questão jurídica." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Executar/ }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect((postMock.mock.calls[0][1] as any).provider).toBe("auto");

    postMock.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Claude" }));
    fireEvent.click(screen.getByRole("button", { name: /Executar/ }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect((postMock.mock.calls[0][1] as any).provider).toBe("anthropic");
  });

  it("Manus só é acionado pela ferramenta explícita de raciocínio profundo", async () => {
    postMock.mockResolvedValue({
      data: {
        status: "running",
        handle: "handle-test",
        provider: "manus",
        modelo: "agent-profile:max",
        conteudo: "",
        alertas: [],
      },
    });
    montar();
    trocarPara("Raciocínio profundo");
    expect(screen.queryByRole("button", { name: "Claude" })).toBeNull();
    fireEvent.change(
      screen.getByPlaceholderText("Descreva o caso ou questão para raciocínio profundo…"),
      { target: { value: "Analise criticamente esta situação jurídica e indique riscos, provas e teses possíveis." } },
    );
    fireEvent.click(screen.getByRole("button", { name: /Executar/ }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][0]).toBe("/manus/deep-reasoning");
    expect(screen.getByTestId("manus-status").textContent).toMatch(/raciocínio profundo/i);
  });

  it("resumir chama /ia/resumir", async () => {
    postMock.mockResolvedValue({ data: RESPOSTA_CANONICA });
    montar();
    trocarPara("Resumir");
    fireEvent.change(screen.getByPlaceholderText("Cole o texto aqui…"), {
      target: { value: "Sentença longa o suficiente para o resumo." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Executar/ }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    expect(postMock.mock.calls[0][0]).toBe("/ia/resumir");
  });

  it("minuta chama /ia/redigir com tipo de peça em opcoes", async () => {
    postMock.mockResolvedValue({ data: RESPOSTA_CANONICA });
    montar();
    trocarPara("Minuta");
    fireEvent.change(
      screen.getByPlaceholderText(/indenização por dano moral/),
      { target: { value: "Dano moral por negativação indevida" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /Executar/ }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    const [rota, corpo] = postMock.mock.calls[0];
    expect(rota).toBe("/ia/redigir");
    expect((corpo as any).opcoes.tipo_peca).toBe("petição inicial");
    expect((corpo as any).texto).toMatch(/Dano moral por negativação indevida/);
  });

  it("especialista chama /ia/analisar com o perfil escolhido", async () => {
    postMock.mockResolvedValue({ data: RESPOSTA_CANONICA });
    montar();
    trocarPara("Especialistas");
    fireEvent.click(screen.getByRole("button", { name: "Financeira" }));
    fireEvent.change(screen.getByPlaceholderText("Cole o texto aqui…"), {
      target: {
        value:
          "Analise a inadimplência da carteira de honorários deste trimestre.",
      },
    });
    fireEvent.click(screen.getByRole("button", { name: /Executar/ }));
    await waitFor(() => expect(postMock).toHaveBeenCalled());
    const [rota, corpo] = postMock.mock.calls[0];
    expect(rota).toBe("/ia/analisar");
    expect((corpo as any).perfil).toBe("financeira");
  });

  it("nenhuma ferramenta chama as portas antigas de IA", async () => {
    postMock.mockResolvedValue({ data: RESPOSTA_CANONICA });
    for (const [rotulo, campo] of [
      ["Pesquisa", "Sua pergunta jurídica…"],
      ["Resumir", "Cole o texto aqui…"],
      ["Traduzir", "Cole o texto aqui…"],
    ] as const) {
      montar();
      trocarPara(rotulo);
      fireEvent.change(screen.getByPlaceholderText(campo), {
        target: { value: "Texto suficientemente longo para enviar." },
      });
      fireEvent.click(screen.getByRole("button", { name: /Executar/ }));
      await waitFor(() => expect(postMock).toHaveBeenCalled());
      cleanup();
    }
    const rotas = postMock.mock.calls.map((c) => c[0]);
    expect(rotas.every((r: string) => r.startsWith("/ia/"))).toBe(true);
    expect(
      rotas.some(
        (r: string) =>
          r.includes("/ai/") || r.includes("/ia-especializada"),
      ),
    ).toBe(false);
  });
});

describe("AssistenteIA — HITL e fontes visíveis", () => {
  it("mostra o aviso de HITL e as fontes do RAG", async () => {
    postMock.mockResolvedValue({ data: RESPOSTA_CANONICA });
    montar();
    fireEvent.change(screen.getByPlaceholderText("Sua pergunta jurídica…"), {
      target: { value: "Qual a tese cabível?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Executar/ }));

    const aviso = await screen.findByTestId("aviso-hitl");
    expect(aviso.textContent).toMatch(/revisão humana/i);

    const fontes = screen.getByTestId("fontes-rag");
    expect(fontes.textContent).toMatch(/Precedente interno 123/);

    expect(screen.getByTestId("motor-ia-usado").textContent).toMatch(/anthropic/i);

    const alertas = screen.getByTestId("alertas-ia");
    expect(alertas.textContent).toMatch(/Citação não confirmada/);
  });

  it("ainda entende o contrato antigo (resposta/fontes/aviso)", async () => {
    postMock.mockResolvedValue({
      data: {
        resposta: "Texto no formato antigo.",
        fontes: [{ titulo: "Fonte antiga" }],
        aviso: "⚠️ Rascunho gerado por IA — revisão humana obrigatória.",
      },
    });
    montar();
    fireEvent.change(screen.getByPlaceholderText("Sua pergunta jurídica…"), {
      target: { value: "Pergunta qualquer." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Executar/ }));

    const aviso = await screen.findByTestId("aviso-hitl");
    expect(aviso.textContent).toMatch(/revisão humana/i);
    expect(screen.getByTestId("fontes-rag").textContent).toMatch(
      /Fonte antiga/,
    );
  });
});

describe("AssistenteIA — limites de caracteres iguais aos do backend", () => {
  it("contador e maxLength acompanham a ferramenta escolhida", () => {
    montar();
    // pesquisa → capacidade conversar (12.000)
    const pergunta = screen.getByPlaceholderText(
      "Sua pergunta jurídica…",
    ) as HTMLTextAreaElement;
    expect(pergunta.maxLength).toBe(12000);
    expect(screen.getByTestId("contador-caracteres").textContent).toMatch(
      /0 \/ 12000 caracteres/,
    );

    fireEvent.change(pergunta, { target: { value: "abcde" } });
    expect(screen.getByTestId("contador-caracteres").textContent).toMatch(
      /5 \/ 12000 caracteres/,
    );

    // resumir → capacidade resumir (200.000)
    trocarPara("Resumir");
    const area = screen.getByPlaceholderText(
      "Cole o texto aqui…",
    ) as HTMLTextAreaElement;
    expect(area.maxLength).toBe(200000);
    expect(screen.getByTestId("contador-caracteres").textContent).toMatch(
      /\/ 200000 caracteres/,
    );
  });

  it("botão fica desabilitado abaixo do mínimo da capacidade", () => {
    montar();
    trocarPara("Especialistas"); // capacidade analisar: mínimo 30
    fireEvent.change(screen.getByPlaceholderText("Cole o texto aqui…"), {
      target: { value: "curto demais" },
    });
    expect(
      (screen.getByRole("button", { name: /Executar/ }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);

    fireEvent.change(screen.getByPlaceholderText("Cole o texto aqui…"), {
      target: {
        value: "Pergunta com mais de trinta caracteres para liberar o envio.",
      },
    });
    expect(
      (screen.getByRole("button", { name: /Executar/ }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
  });
});
