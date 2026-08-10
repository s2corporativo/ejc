// @vitest-environment jsdom
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
const patchMock = vi.fn();
const toastErrorMock = vi.fn();

vi.mock("../lib/api", () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    patch: (...args: unknown[]) => patchMock(...args),
  },
  getAccessToken: () => null,
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

vi.mock("../components/Toast", () => ({
  toast: {
    success: vi.fn(),
    error: (...args: unknown[]) => toastErrorMock(...args),
    info: vi.fn(),
  },
}));

vi.mock("../stores/auth", () => ({
  useAuth: () => ({ user: { id: "u1", full_name: "Dra. Advogada" } }),
}));

vi.mock("../components/Markdown", () => ({
  default: ({ source }: { source: string }) => <div>{source}</div>,
}));

import SalaJuridica from "./SalaJuridica";

const SESSAO = {
  id: "s1",
  titulo: "Análise de consistência",
  status: "em_analise",
  favorita: false,
  cliente_potencial: null,
  area_sugerida: "civil",
  workspace_versao: 1,
  convertido_case_id: null,
  frozen: false,
  custo_ia_total: 0,
  workspace_texto: "Contexto salvo anteriormente.",
  mensagens: [],
  anexos: [],
  estado: null,
};

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  patchMock.mockReset();
  toastErrorMock.mockReset();
  Element.prototype.scrollTo = vi.fn();

  getMock.mockImplementation((url: string) => {
    if (url === "/sala-juridica") return Promise.resolve({ data: [SESSAO] });
    if (url === "/sala-juridica/s1") return Promise.resolve({ data: SESSAO });
    return Promise.resolve({ data: {} });
  });
});

afterEach(cleanup);

describe("Sala Jurídica — consistência workspace → IA", () => {
  it("não envia mensagem à IA quando o flush do workspace falha", async () => {
    patchMock.mockRejectedValueOnce(new Error("falha simulada de persistência"));

    render(
      <MemoryRouter initialEntries={["/sala-juridica"]}>
        <SalaJuridica />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue("Contexto salvo anteriormente.")).toBeTruthy();
    });

    fireEvent.change(
      screen.getByPlaceholderText(
        "Cole fatos, narrativas do cliente, rascunhos, trechos de peças…",
      ),
      { target: { value: "Contexto jurídico ainda não persistido." } },
    );

    const mensagem = screen.getByPlaceholderText(
      "Converse livremente ou dê um comando jurídico…",
    ) as HTMLTextAreaElement;
    fireEvent.change(mensagem, {
      target: { value: "Analise o contexto atualizado." },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Enviar$/i }));

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith("/sala-juridica/s1", {
        workspace_texto: "Contexto jurídico ainda não persistido.",
      });
      expect(toastErrorMock).toHaveBeenCalledWith(
        expect.stringMatching(/mensagem não foi enviada/i),
      );
    });

    expect(postMock).not.toHaveBeenCalled();
    expect(mensagem.value).toBe("Analise o contexto atualizado.");
  });
});
