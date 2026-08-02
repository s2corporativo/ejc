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
import { MemoryRouter } from "react-router-dom";

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
  prazo: {
    descricao: "15 dias úteis a partir de 12/07/2026",
    data: "2026-08-02",
    origem: "fls. 2 da notificação",
    requer_confirmacao_humana: true,
  },
  proxima_acao: "Notificação extrajudicial",
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

    // Documentos com classificação e não reconhecido
    expect(screen.getByText("Comprovante de pagamento")).toBeTruthy();
    expect(screen.getByText("comprovante")).toBeTruthy();
    expect(screen.getByText("não reconhecido")).toBeTruthy();

    // Blocos por exceção: conflito, duplicado e prazo
    expect(screen.getByText(/CONFLITO DE INTERESSES — 1 achado/)).toBeTruthy();
    expect(screen.getByText(/consta como cliente ativo/)).toBeTruthy();
    expect(
      screen.getByText("Cliente possivelmente já cadastrado"),
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
