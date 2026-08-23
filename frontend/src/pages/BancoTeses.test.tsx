// @vitest-environment jsdom
// Banco de Teses — duas capacidades, uma tela:
//   • varredura reversa (tese → casos), que converte catálogo em ferramenta;
//   • radar regulatório (publicação → teses), que diz o que RELER.
// Os testes cobrem o que quebraria em silêncio:
//   • a varredura só dispara para a tese CLICADA (e no endpoint certo);
//   • cada candidato mostra os termos que casaram — score sem justificativa
//     convida o advogado a confiar sem conferir;
//   • lista vazia não vira tela em branco;
//   • o teto de varredura é avisado, senão "nenhum candidato" pode significar
//     "não procurei em tudo" sem ninguém saber;
//   • o radar falha em SILÊNCIO: painel acessório não derruba a página.
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

const VARREDURA = {
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
};

const IMPACTO = {
  periodo_dias: 7,
  publicacoes_varridas: 12,
  total: 1,
  teses_afetadas: [
    {
      tese_id: "t1",
      titulo: TESE.titulo,
      area_juridica: "civil",
      score_maximo: 70,
      total_publicacoes: 3,
      publicacoes: [
        {
          alerta_id: "a1",
          fonte: "dou",
          titulo: "Decisão sobre purgação da mora",
          link: "https://exemplo.gov.br/a1",
          data_publicacao: "2026-08-20",
          area_classificada: "civil",
          score: 70,
          termos_casados: ["purgacao"],
          area_alinhada: true,
        },
      ],
    },
  ],
  aviso: "Indica o que RELER, não o que está superado.",
};

/** Despacha por URL: a página faz DUAS chamadas na montagem (catálogo e
 *  radar), então mock em sequência tornaria os testes dependentes da ordem de
 *  resolução — que é justamente o que não se deve fixar. */
function mockApi({
  teses = [TESE] as unknown[],
  varredura = VARREDURA as unknown,
  impacto = IMPACTO as unknown,
}: {
  teses?: unknown[];
  varredura?: unknown;
  impacto?: unknown | Error;
} = {}) {
  getMock.mockImplementation((url: string) => {
    if (url === "/teses") return Promise.resolve({ data: teses });
    if (url === "/teses/impacto-regulatorio") {
      return impacto instanceof Error
        ? Promise.reject(impacto)
        : Promise.resolve({ data: impacto });
    }
    if (url.endsWith("/casos-candidatos"))
      return Promise.resolve({ data: varredura });
    return Promise.reject(new Error(`URL inesperada: ${url}`));
  });
}

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
    mockApi();
    renderPagina();
    expect(await screen.findAllByText(TESE.titulo)).toBeTruthy();
    expect(getMock).toHaveBeenCalledWith("/teses", {
      params: { status: "ativa", limit: 200 },
    });
  });

  it("varre os casos da tese clicada e mostra os termos que casaram", async () => {
    mockApi();
    renderPagina();
    const alvos = await screen.findAllByText(TESE.titulo);
    fireEvent.click(alvos[alvos.length - 1]); // o item do catálogo

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
    mockApi({
      varredura: { ...VARREDURA, total: 0, candidatos: [], aviso: undefined },
    });
    renderPagina();
    const alvos = await screen.findAllByText(TESE.titulo);
    fireEvent.click(alvos[alvos.length - 1]);

    expect(await screen.findByText("Nenhum processo aderente")).toBeTruthy();
  });

  it("avisa quando o teto de varredura foi atingido", async () => {
    mockApi({
      varredura: {
        ...VARREDURA,
        casos_varridos: 2000,
        teto_de_varredura_atingido: true,
        total: 0,
        candidatos: [],
      },
    });
    renderPagina();
    const alvos = await screen.findAllByText(TESE.titulo);
    fireEvent.click(alvos[alvos.length - 1]);

    expect(await screen.findByText(/Teto de varredura atingido/)).toBeTruthy();
  });

  it("orienta o usuário antes de qualquer tese ser escolhida", async () => {
    mockApi();
    renderPagina();
    expect(await screen.findByText("Escolha uma tese")).toBeTruthy();
  });

  it("mostra as teses que o Diário pode ter afetado, com a publicação", async () => {
    mockApi();
    renderPagina();

    expect(
      await screen.findByText("Teses a reler pelo que saiu no Diário"),
    ).toBeTruthy();
    const pub = await screen.findByText("Decisão sobre purgação da mora");
    expect(pub.getAttribute("href")).toBe("https://exemplo.gov.br/a1");
    // O total real precisa aparecer: "1 publicação" não pode ser lido como
    // "só existe 1" quando existem 3.
    expect(screen.getByText(/\+2 outra\(s\) publicação\(ões\)/)).toBeTruthy();
    expect(screen.getByText(/não o que está superado/)).toBeTruthy();
  });

  it("não quebra a página quando o radar regulatório falha", async () => {
    mockApi({ impacto: new Error("503") });
    renderPagina();

    // O catálogo continua de pé…
    expect(await screen.findAllByText(TESE.titulo)).toBeTruthy();
    // …e o painel simplesmente não aparece.
    expect(
      screen.queryByText("Teses a reler pelo que saiu no Diário"),
    ).toBeNull();
  });
});
