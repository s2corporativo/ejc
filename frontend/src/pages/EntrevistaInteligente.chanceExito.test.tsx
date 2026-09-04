// @vitest-environment jsdom
// V2-4.2 (plano-mestre) / decisão D4 — a métrica "chance de êxito" (percentual
// GERADO POR IA, com barra colorida) deixou de ser exibida na Entrevista
// Inteligente: risco Código de Ética OAB art. 34, XXIX (vedação a captação/
// mercantilização inadequada da expectativa do cliente) + fragilidade
// estatística (poucos casos para calibrar). A API continua devolvendo o
// campo `chance_exito` (não foi removido do contrato) — só a renderização
// foi retirada. Este teste prova que o painel de triagem não expõe mais o
// percentual nem a justificativa, mesmo quando a resposta os traz.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";

const postMock = vi.fn();

vi.mock("../lib/api", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: (...a: unknown[]) => postMock(...a),
    patch: vi.fn().mockResolvedValue({ data: {} }),
  },
  getAccessToken: () => null,
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

vi.mock("../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import EntrevistaInteligente from "./EntrevistaInteligente";

const RESPOSTA_COM_CHANCE_EXITO = {
  status: "ok",
  aviso: "",
  case_id: null,
  parse_ok: true,
  pii_removida: false,
  modelo: "modelo-teste",
  ai_log_id: "log-1",
  analise: {
    area_direito: { valor: "Cível", confianca: 80 },
    competencia: { valor: "Estadual", confianca: 80 },
    possivel_acao: { valor: "Indenizatória", confianca: 80 },
    urgencia: { valor: false, confianca: 80 },
    tutela_liminar: { valor: false, confianca: 80 },
    prescricao: { dentro_prazo: true, alerta: null, confianca: 80 },
    valor_causa: { valor: 1000, confianca: 80 },
    pedidos_possiveis: [],
    riscos: [],
    chance_exito: {
      percentual: 87,
      justificativa: "Justificativa que não deve mais aparecer na tela.",
      confianca: 90,
    },
  },
};

beforeEach(() => {
  postMock.mockReset();
  postMock.mockResolvedValue({ data: RESPOSTA_COM_CHANCE_EXITO });
});

afterEach(() => {
  cleanup();
});

function renderPagina() {
  return render(
    <MemoryRouter initialEntries={["/entrevista"]}>
      <EntrevistaInteligente />
    </MemoryRouter>,
  );
}

describe("EntrevistaInteligente — chance de êxito não é mais exibida (D4)", () => {
  it("não renderiza percentual, badge de êxito nem a justificativa mesmo quando a API os devolve", async () => {
    renderPagina();

    const textarea = screen.getByPlaceholderText(/Descreva o ocorrido/i);
    fireEvent.change(textarea, {
      target: { value: "a".repeat(50) },
    });
    fireEvent.click(screen.getByRole("button", { name: /Analisar/i }));

    await waitFor(() => expect(postMock).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getAllByText(/Área do Direito/i).length).toBeGreaterThan(0),
    );

    expect(screen.queryByText(/87% de êxito estimado/i)).toBeNull();
    expect(screen.queryByText(/chance de êxito/i)).toBeNull();
    expect(
      screen.queryByText(/Justificativa que não deve mais aparecer na tela/i),
    ).toBeNull();
  });
});
