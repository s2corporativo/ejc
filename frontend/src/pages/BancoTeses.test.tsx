// @vitest-environment jsdom
// Banco de Teses — a varredura reversa (tese → casos) é o que converte o
// catálogo em ferramenta de trabalho. Cobre o que quebraria em silêncio:
//   • a varredura só dispara para a tese CLICADA (e no endpoint certo);
//   • cada candidato mostra os termos que casaram — score sem justificativa
//     convida o advogado a confiar sem conferir;
//   • lista vazia não vira tela em branco;
//   • o teto de varredura é avisado, senão "nenhum candidato" pode significar
//     "não procurei em tudo" sem ninguém saber.
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

vi.mock("../lib/api", () => ({
  default: { get: (...a: unknown[]) => getMock(...a) },
  getAccessToken: () => null,
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

vi.mock("../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import BancoTeses from "./BancoTeses";

const TESE = {
  id: "t1",
  titulo: "Purgação da mora na busca e apreensão",
  descricao: "Tese sobre purgação.",
  area_juridica: "civil",
  vezes_usada: 4,
  vezes_venceu: 3,
};

function renderPagina() {
  return render(
    <MemoryRouter>
      <BancoTeses />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  getMock.mockReset();
});

afterEach(() => cleanup());

describe("Banco de Teses", () => {
  it("lista as teses ativas do escritório", async () => {
    getMock.mockResolvedValueOnce({ data: [TESE] });
    renderPagina();
    expect(
      await screen.findByText("Purgação da mora na busca e apreensão"),
    ).toBeTruthy();
    expect(getMock).toHaveBeenCalledWith("/teses", {
      params: { status: "ativa", limit: 200 },
    });
  });

  it("varre os casos da tese clicada e mostra os termos que casaram", async () => {
    getMock.mockResolvedValueOnce({ data: [TESE] }).mockResolvedValueOnce({
      data: {
        tese_id: "t1",
        titulo: TESE.titulo,
        termos: ["purgacao", "mora"],
        casos_varridos: 12,
        total: 1,
        candidatos: [
          {
            case_id: "c1",
            numero_interno: "DPT-2026-0001",
            titulo: "Busca e apreensão de veículo",
            area: "civil",
            status: "aberto",
            score: 55,
            termos_casados: ["purgacao", "mora"],
            area_coincide: true,
          },
        ],
        aviso: "Sugestão determinística — conferir antes de vincular.",
      },
    });

    renderPagina();
    fireEvent.click(await screen.findByText(TESE.titulo));

    await waitFor(() =>
      expect(getMock).toHaveBeenCalledWith("/teses/t1/casos-candidatos", {
        params: { limite: 20 },
      }),
    );

    expect(
      await screen.findByText(/DPT-2026-0001 — Busca e apreensão de veículo/),
    ).toBeTruthy();
    // Justificativa visível: sem ela o score é um número sem lastro.
    expect(screen.getAllByText("purgacao").length).toBeGreaterThan(0);
    expect(screen.getByText("mesma área")).toBeTruthy();
    expect(screen.getByText(/conferir antes de vincular/)).toBeTruthy();
  });

  it("explica o vazio quando nenhum processo casa a tese", async () => {
    getMock.mockResolvedValueOnce({ data: [TESE] }).mockResolvedValueOnce({
      data: {
        tese_id: "t1",
        titulo: TESE.titulo,
        termos: ["purgacao"],
        casos_varridos: 12,
        total: 0,
        candidatos: [],
      },
    });

    renderPagina();
    fireEvent.click(await screen.findByText(TESE.titulo));

    expect(await screen.findByText("Nenhum processo aderente")).toBeTruthy();
  });

  it("avisa quando o teto de varredura foi atingido", async () => {
    getMock.mockResolvedValueOnce({ data: [TESE] }).mockResolvedValueOnce({
      data: {
        tese_id: "t1",
        titulo: TESE.titulo,
        termos: ["purgacao"],
        casos_varridos: 2000,
        teto_de_varredura_atingido: true,
        total: 0,
        candidatos: [],
      },
    });

    renderPagina();
    fireEvent.click(await screen.findByText(TESE.titulo));

    expect(await screen.findByText(/Teto de varredura atingido/)).toBeTruthy();
  });

  it("orienta o usuário antes de qualquer tese ser escolhida", async () => {
    getMock.mockResolvedValueOnce({ data: [TESE] });
    renderPagina();
    expect(await screen.findByText("Escolha uma tese")).toBeTruthy();
  });
});
