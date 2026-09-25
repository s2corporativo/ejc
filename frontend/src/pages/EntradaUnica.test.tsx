// @vitest-environment jsdom
// Entrada Única (/entrada) — cobre o que sustenta o fluxo de duas telas:
//   • a tela inicial (wireframe A.1) renderiza relato + dropzone + limites;
//   • [Analisar] só habilita com relato ≥ 40 caracteres OU ≥ 1 arquivo;
//   • a confirmação (tela B) renderiza o payload COMPLETO do contrato,
//     incluindo os blocos por exceção (conflito, duplicado, prazo) e os
//     gates que habilitam [Criar caso];
//   • resposta degradada NUNCA vira tela de erro — vira confirmação vazia
//     com o banner âmbar (wireframe A.3).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("../lib/api", () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
    post: (...a: unknown[]) => postMock(...a),
  },
  getAccessToken: () => null,
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

vi.mock("../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock("../stores/auth", () => ({
  useAuth: () => ({
    user: { id: "u1", full_name: "Dr. Clovis", role: "advogado" },
  }),
}));

import EntradaUnica from "./EntradaUnica";

const RESPOSTA_COMPLETA = {
  rascunho_id: "r1",
  cliente: {
    client_id: "c9",
    nome: "Maria S. da Costa",
    origem: "CPF no comprovante de pagamento",
    confianca: 0.92,
    ja_cadastrada: true,
    casos_anteriores: 2,
  },
  area: { valor: "consumidor", confianca: 0.8 },
  assunto: { valor: "Negativação indevida", confianca: 0.88 },
  natureza: {
    tipo: "judicial",
    acao: "Ação declaratória de inexistência de débito",
    confianca: 0.82,
  },
  urgencia: {
    valor: true,
    prioridade_sugerida: "alta",
    justificativa: "Restrição de crédito ativa.",
    confianca: 0.79,
  },
  titulo: "Negativação indevida — Maria S. da Costa",
  fatos: "Negativação indevida após quitação do contrato em 12/03/2026.",
  parte_contraria: "Banco X S/A",
  documentos: [
    {
      document_id: "d1",
      nome: "Comprovante de pagamento",
      classificacao: "comprovante",
      confianca: 0.95,
    },
    { document_id: "d2", nome: "Contrato", classificacao: null },
  ],
  documentos_faltantes: ["Consulta atualizada do cadastro restritivo"],
  provas_necessarias: ["Confirmar data da negativação"],
  prazo: {
    descricao: "15 dias úteis a partir de 12/07/2026",
    data: "2026-08-02",
    origem: "fls. 2 da notificação",
    requer_confirmacao_humana: true,
  },
  proxima_acao: "Notificação extrajudicial",
  proximos_passos: ["Conferir quitação", "Avaliar tutela de urgência"],
  conflito: {
    alertas: ['Parte contrária "Banco X S/A" consta como cliente ativo.'],
  },
  duplicados: {
    clientes: [{ client_id: "c10", nome: "Maria Souza da Costa" }],
  },
  degradado: false,
  avisos: [],
};

function montar() {
  return render(
    <MemoryRouter>
      <EntradaUnica />
    </MemoryRouter>,
  );
}

function preencherRelato(chars: number) {
  fireEvent.change(screen.getByLabelText("Relato do cliente"), {
    target: { value: "x".repeat(chars) },
  });
}

beforeEach(() => {
  sessionStorage.clear();
  getMock.mockReset();
  postMock.mockReset();
  getMock.mockImplementation((url: string) => {
    if (String(url).includes("/entrada-universal/meta")) {
      return Promise.resolve({
        data: { max_arquivos: 40, max_lote_mb: 120, formatos: [".pdf"] },
      });
    }
    if (String(url).includes("/users")) {
      return Promise.resolve({
        data: [
          {
            id: "u1",
            full_name: "Dr. Clovis",
            role: "advogado",
            email: "c@x",
            is_active: true,
          },
        ],
      });
    }
    return Promise.resolve({ data: { data: [] } });
  });
});

afterEach(() => {
  cleanup();
});

describe("EntradaUnica — tela inicial (A.1)", () => {
  it("renderiza relato, dropzone com limites e botão Analisar desabilitado", async () => {
    montar();
    expect(
      screen.getByPlaceholderText("Cole aqui o que o cliente contou."),
    ).toBeTruthy();
    expect(
      screen.getByText(/Arraste documentos aqui · ou clique para escolher/),
    ).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByText(/até 40 arquivos, 120 MB/)).toBeTruthy(),
    );
    const botao = screen.getByRole("button", {
      name: "Analisar",
    }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
  });

  it("habilita Analisar com relato ≥ 40 caracteres OU ≥ 1 arquivo", () => {
    montar();
    const botao = screen.getByRole("button", {
      name: "Analisar",
    }) as HTMLButtonElement;

    preencherRelato(39);
    expect(botao.disabled).toBe(true);

    preencherRelato(40);
    expect(botao.disabled).toBe(false);

    // Sem relato, um arquivo basta.
    preencherRelato(0);
    expect(botao.disabled).toBe(true);
    const input = screen.getByTestId("entrada-file-input");
    fireEvent.change(input, {
      target: {
        files: [new File(["x"], "doc.pdf", { type: "application/pdf" })],
      },
    });
    expect(botao.disabled).toBe(false);
  });
});

describe("EntradaUnica — confirmação (tela B)", () => {
  it("renderiza o payload completo com blocos por exceção e gates", async () => {
    postMock.mockResolvedValueOnce({ data: RESPOSTA_COMPLETA });
    montar();
    preencherRelato(60);
    fireEvent.click(screen.getByRole("button", { name: "Analisar" }));

    await screen.findByText("Confira e confirme");

    // Campos inferidos, todos editáveis
    expect(
      (screen.getByLabelText("Título do caso") as HTMLInputElement).value,
    ).toBe("Negativação indevida — Maria S. da Costa");
    expect(
      (screen.getByLabelText("Área do caso") as HTMLSelectElement).value,
    ).toBe("consumidor");
    expect(screen.getByText("Maria S. da Costa")).toBeTruthy();
    expect(
      screen.getByText(/origem: CPF no comprovante de pagamento/),
    ).toBeTruthy();
    expect(
      (screen.getByLabelText("Parte contrária") as HTMLInputElement).value,
    ).toBe("Banco X S/A");
    expect(
      (screen.getByLabelText("Assunto jurídico") as HTMLInputElement).value,
    ).toBe("Negativação indevida");
    expect(
      (screen.getByLabelText("Natureza da demanda") as HTMLSelectElement).value,
    ).toBe("judicial");
    expect(
      (screen.getByLabelText("Possível ação ou procedimento") as HTMLInputElement)
        .value,
    ).toBe("Ação declaratória de inexistência de débito");
    expect(
      (screen.getByLabelText("Prioridade do caso") as HTMLSelectElement).value,
    ).toBe("alta");
    expect(
      (screen.getByLabelText("Motivo da urgência") as HTMLTextAreaElement).value,
    ).toBe("Restrição de crédito ativa.");
    expect(
      (screen.getByLabelText("Documentos faltantes") as HTMLTextAreaElement)
        .value,
    ).toContain("Consulta atualizada");
    expect(
      (screen.getByLabelText("Provas necessárias") as HTMLTextAreaElement).value,
    ).toContain("Confirmar data");
    expect(
      (screen.getByLabelText("Próximos passos") as HTMLTextAreaElement).value,
    ).toContain("Avaliar tutela");

    // Documentos com classificação e não reconhecido
    expect(screen.getByText("Comprovante de pagamento")).toBeTruthy();
    expect(screen.getByText("comprovante")).toBeTruthy();
    expect(screen.getByText("não reconhecido")).toBeTruthy();

    // Blocos por exceção: conflito, duplicado e prazo
    expect(screen.getByText(/CONFLITO DE INTERESSES — 1 achado/)).toBeTruthy();
    expect(screen.getByText(/consta como cliente ativo/)).toBeTruthy();
    // Com cliente EXISTENTE identificado, o bloco de duplicidade fala de
    // casos ativos (review do Bloco 3) — e o checkbox de reconhecimento
    // agora renderiza também nesse caminho.
    expect(
      screen.getByText(
        "Este cliente possui caso ativo — confira se não é o mesmo assunto",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Conferi os casos ativos e confirmo que este é um caso NOVO",
      ),
    ).toBeTruthy();
    expect(screen.getByText("criar este prazo")).toBeTruthy();
    expect(screen.getByText(/origem: fls\. 2 da notificação/)).toBeTruthy();

    // Gates: só o checkbox final não basta quando há conflito
    const criar = screen.getByRole("button", {
      name: "Criar caso",
    }) as HTMLButtonElement;
    expect(criar.disabled).toBe(true);
    fireEvent.click(
      screen.getByLabelText("Confirmo que revisei os dados acima"),
    );
    expect(criar.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("Revisei e não há impedimento"));
    // Terceiro gate (review do Bloco 3): cliente existente com caso ativo
    // também exige reconhecimento explícito de duplicidade.
    expect(criar.disabled).toBe(true);
    fireEvent.click(
      screen.getByLabelText(
        "Conferi os casos ativos e confirmo que este é um caso NOVO",
      ),
    );
    expect(criar.disabled).toBe(false);
  });

  it("degradado=true vira confirmação vazia com banner âmbar, nunca tela de erro", async () => {
    postMock.mockResolvedValueOnce({
      data: { rascunho_id: "r2", degradado: true, avisos: [] },
    });
    montar();
    preencherRelato(60);
    fireEvent.click(screen.getByRole("button", { name: "Analisar" }));

    await screen.findByText("Confira e confirme");
    expect(
      screen.getByText(/A análise por IA está indisponível agora/),
    ).toBeTruthy();
    // Campos vêm vazios e editáveis
    expect(
      (screen.getByLabelText("Título do caso") as HTMLInputElement).value,
    ).toBe("");
    expect(
      (screen.getByLabelText("Fatos do caso") as HTMLTextAreaElement).value,
    ).toBe("");
    // O caminho SEMPRE chega ao botão de criar
    expect(screen.getByRole("button", { name: "Criar caso" })).toBeTruthy();
  });

  it("rascunho sobrevive ao F5 (reidrata do sessionStorage)", async () => {
    postMock.mockResolvedValueOnce({ data: RESPOSTA_COMPLETA });
    const primeira = montar();
    preencherRelato(60);
    fireEvent.click(screen.getByRole("button", { name: "Analisar" }));
    await screen.findByText("Confira e confirme");
    primeira.unmount();

    // Remontagem simulando F5: sem novo POST, a proposta volta da sessão.
    montar();
    await screen.findByText("Confira e confirme");
    expect(
      (screen.getByLabelText("Título do caso") as HTMLInputElement).value,
    ).toBe("Negativação indevida — Maria S. da Costa");
  });
});

// ── Regressão do contrato (code review do Bloco 3) — funções puras ───────────
import {
  EH_CNJ,
  EH_DATA_ISO,
  confiancaPct,
  montarPayloadCriacao,
  normalizarAnalise,
  textoDeAchado,
  type Proposta,
} from "./EntradaUnica/types";

function propostaBase(extra: Partial<Proposta>): Proposta {
  const p = normalizarAnalise(
    { rascunho_id: "b1", cliente: {}, area: {}, documentos: [] },
    "eu-1",
  );
  if (!p) throw new Error("proposta base inválida");
  return { ...p, titulo: "Caso teste", area: "civil", ...extra };
}

describe("contrato criar-caso (regressões do review)", () => {
  it("prazo só entra no payload com data ISO válida", () => {
    const comIso = montarPayloadCriacao(
      propostaBase({
        prazo: {
          descricao: "Contestar",
          data: "2026-09-15",
          origem: null,
          requerConfirmacao: true,
          criar: true,
          responsavelId: "eu-1",
        },
      }),
    );
    expect((comIso.prazo as { data: string }).data).toBe("2026-09-15");

    const semIso = montarPayloadCriacao(
      propostaBase({
        prazo: {
          descricao: "Contestar",
          data: "15/09/2026",
          origem: null,
          requerConfirmacao: true,
          criar: true,
          responsavelId: "eu-1",
        },
      }),
    );
    expect(semIso.prazo).toBeUndefined();
  });

  it("leva triagem revisada ao payload de criação", () => {
    const payload = montarPayloadCriacao(
      propostaBase({
        assunto: "Negativação indevida",
        naturezaDemanda: "judicial",
        naturezaProvavel: "Ação declaratória",
        prioridade: "alta",
        urgenciaMotivo: "Restrição ativa",
        documentosFaltantes: ["Consulta atualizada"],
        provasNecessarias: ["Confirmar data"],
        proximosPassos: ["Conferir quitação"],
      }),
    );
    expect(payload.assunto).toBe("Negativação indevida");
    expect(payload.natureza_demanda).toBe("judicial");
    expect(payload.natureza_provavel).toBe("Ação declaratória");
    expect(payload.prioridade).toBe("alta");
    expect(payload.urgencia_motivo).toBe("Restrição ativa");
    expect(payload.documentos_faltantes).toEqual(["Consulta atualizada"]);
    expect(payload.provas_necessarias).toEqual(["Confirmar data"]);
    expect(payload.proximos_passos).toEqual(["Conferir quitação"]);
  });

  it("escolher cliente existente NÃO auto-confirma duplicidade (gate do servidor)", () => {
    const payload = montarPayloadCriacao(
      propostaBase({
        clienteId: "c-1",
        duplicados: [{ clientId: "c-1", rotulo: "Maria" }],
        duplicateConfirmed: false,
      }),
    );
    expect(payload.duplicate_confirmed).toBe(false);
  });

  it("conflict_confirmed acompanha o reconhecimento mesmo sem achado local", () => {
    const payload = montarPayloadCriacao(
      propostaBase({ conflitoAlertas: [], conflictConfirmed: true }),
    );
    expect(payload.conflict_confirmed).toBe(true);
  });

  it("normalizador aceita ja_cadastrado (chave real do backend) e confiança textual", () => {
    const p = normalizarAnalise(
      {
        rascunho_id: "b2",
        cliente: {
          client_id: "c-9",
          nome: "Maria",
          ja_cadastrado: true,
          casos_anteriores: 2,
          confianca: "alta",
        },
      },
      "eu-1",
    );
    expect(p?.clienteJaCadastrada).toBe(true);
    expect(p?.clienteCasosAnteriores).toBe(2);
    expect(p?.clienteConfianca).toBe(90);
    expect(confiancaPct("baixa")).toBe(30);
  });

  it("textoDeAchado trata array de detail 422 sem virar [object Object]", () => {
    const texto = textoDeAchado([
      { msg: "data inválida", loc: ["body", "prazo"] },
      "outro problema",
    ]);
    expect(texto).toContain("data inválida");
    expect(texto).toContain("outro problema");
    expect(texto).not.toContain("[object Object]");
  });

  it("prazo com data não-ISO do backend vira campo vazio (não envia lixo)", () => {
    const p = normalizarAnalise(
      {
        rascunho_id: "b3",
        prazo: { descricao: "Prazo", data: null, data_texto: "15/09/2026" },
      },
      "eu-1",
    );
    expect(p?.prazo?.data).toBe("");
    expect(p?.prazo?.descricao).toContain("15/09/2026");
    expect(EH_DATA_ISO.test("2026-01-02")).toBe(true);
  });
});


describe("reconciliação processual na Entrada Única", () => {
  it("normaliza CNJ e correspondência provável sem auto-confirmar duplicidade", () => {
    const p = normalizarAnalise(
      {
        rascunho_id: "proc-1",
        numero_cnj: "0709938-44.2026.8.07.0018",
        reconciliacao_processual: {
          status: "provavel_correspondencia",
          numero_cnj_principal: "0709938-44.2026.8.07.0018",
          cnjs_detectados: ["0709938-44.2026.8.07.0018"],
          bloquear_criacao: false,
          acao_sugerida: "revisar_e_vincular_pre_processual",
          mensagem: "Há caso existente com forte correspondência.",
          correspondencias: [
            {
              case_id: "case-64",
              numero_interno: "DPT-2026-0064",
              titulo: "Betim Baterias x DER/DF",
              score: 95,
              motivos: ["mesmo cliente", "caso pré-processual pode ter sido ajuizado"],
              pode_converter_pre_processual: true,
              protegido: false,
            },
          ],
        },
      },
      "eu-1",
    );
    expect(p?.numeroCnj).toBe("0709938-44.2026.8.07.0018");
    expect(p?.reconciliacaoProcessual.status).toBe("provavel_correspondencia");
    expect(
      p?.reconciliacaoProcessual.correspondencias[0]
        ?.podeConverterPreProcessual,
    ).toBe(true);
    expect(p?.duplicateConfirmed).toBe(false);
    expect(p?.processMatchConfirmed).toBe(false);
    expect(EH_CNJ.test(p?.numeroCnj ?? "")).toBe(true);

    const payload = montarPayloadCriacao(p as Proposta);
    expect(payload.numero_cnj).toBe("0709938-44.2026.8.07.0018");
    expect(payload.duplicate_confirmed).toBeUndefined();
    expect(payload.process_match_confirmed).toBe(false);
  });

  it("CNJ já cadastrado é exibido como bloqueio processual", async () => {
    postMock.mockResolvedValueOnce({
      data: {
        rascunho_id: "proc-2",
        numero_cnj: "1018284-13.2026.8.13.0027",
        reconciliacao_processual: {
          status: "ja_cadastrado",
          numero_cnj_principal: "1018284-13.2026.8.13.0027",
          cnjs_detectados: ["1018284-13.2026.8.13.0027"],
          bloquear_criacao: true,
          acao_sugerida: "abrir_caso_existente",
          mensagem: "O CNJ informado já está vinculado a um registro do EJC.",
          correspondencias: [
            {
              case_id: "case-1",
              numero_interno: "DPT-2026-0001",
              titulo: "Caso existente",
              score: 100,
              motivos: ["CNJ idêntico já cadastrado"],
              pode_converter_pre_processual: false,
              protegido: false,
            },
          ],
        },
      },
    });
    montar();
    preencherRelato(60);
    fireEvent.click(screen.getByRole("button", { name: "Analisar" }));

    await screen.findByText("Reconciliação processual");
    expect(screen.getByText("já cadastrado")).toBeTruthy();
    expect(
      screen.getByText(/Outro caso não será criado/),
    ).toBeTruthy();

    fireEvent.click(
      screen.getByLabelText("Confirmo que revisei os dados acima"),
    );
    expect(
      (screen.getByRole("button", { name: "Criar caso" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });
});
