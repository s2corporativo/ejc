// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("../lib/api", () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}));

import {
  pesquisarFontesJuridicas,
  verificarCitacoesJuridicas,
} from "./legalResearch";

afterEach(() => {
  getMock.mockReset();
  postMock.mockReset();
});

describe("legalResearch — contratos canônicos", () => {
  it("pesquisa usa o pipeline governado do RAG", async () => {
    getMock.mockResolvedValue({
      data: {
        query: "dano moral",
        modo: "semantica",
        pipeline: "hibrida_governada",
        resultados: [{ titulo: "REsp teste", chunk_id: "chunk-1" }],
      },
    });

    const data = await pesquisarFontesJuridicas("dano moral", 10);

    expect(getMock).toHaveBeenCalledWith("/rag/buscar", {
      params: { q: "dano moral", limite: 10 },
    });
    expect(data.pipeline).toBe("hibrida_governada");
    expect(data.resultados).toHaveLength(1);
  });

  it("validação de citações usa o verificador determinístico", async () => {
    postMock.mockResolvedValue({
      data: {
        total: 1,
        confirmadas: 1,
        nao_encontradas: 0,
        score: 100,
        aviso: "Conferir fonte oficial.",
        avisos: ["Conferir fonte oficial."],
        citacoes: [
          {
            citacao: "Súmula 1 STJ",
            tipo: "sumula",
            encontrada: true,
            status: "verificada",
          },
        ],
      },
    });

    const data = await verificarCitacoesJuridicas(
      "Conforme Súmula 1 STJ.",
      true,
    );

    expect(postMock).toHaveBeenCalledWith("/ai/citacoes/verificar", {
      texto: "Conforme Súmula 1 STJ.",
      consultar_datajud: true,
    });
    expect(data.score).toBe(100);
    expect(data.citacoes[0].status).toBe("verificada");
  });

  it("normaliza listas ausentes sem inventar resultados", async () => {
    getMock.mockResolvedValue({
      data: { query: "teste", modo: "textual", pipeline: "hibrida_governada" },
    });
    postMock.mockResolvedValue({
      data: {
        total: 0,
        confirmadas: 0,
        nao_encontradas: 0,
        score: null,
        aviso: "Nenhuma citação detectada.",
      },
    });

    const pesquisa = await pesquisarFontesJuridicas("teste");
    const verificacao = await verificarCitacoesJuridicas("texto", false);

    expect(pesquisa.resultados).toEqual([]);
    expect(verificacao.citacoes).toEqual([]);
    expect(verificacao.avisos).toEqual([]);
  });
});
