// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import Jurimetria from "./Jurimetria";

const getMock = vi.fn();

vi.mock("../lib/api", () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
  },
}));

vi.mock("../stores/auth", () => ({
  useAuth: (selector: (state: { user: { role: string } }) => unknown) =>
    selector({ user: { role: "socio" } }),
}));

function resposta(url: string) {
  if (url === "/jurimetria/desfechos") {
    return {
      data: {
        total_encerrados: 0,
        por_resultado: [],
        licoes_aprendidas: [],
      },
    };
  }
  if (url === "/jurimetria/overview") {
    return { data: { taxa_sucesso_geral: 0.5 } };
  }
  if (url === "/jurimetria/por-area") return { data: [] };
  if (url === "/jurimetria/por-tribunal") return { data: [] };
  if (url === "/jurimetria/por-tese") return { data: [] };
  if (url === "/jurimetria/interno/stats") {
    return {
      data: {
        fonte: "base interna",
        total_com_tribunal: 123,
        // Top 15 é apenas breakdown; a soma deliberadamente não representa o total.
        por_tribunal: [{ tribunal: "TJMG", total: 12 }],
      },
    };
  }
  if (url === "/jurimetria/cobertura-rag") {
    return { data: { documentos: 100, chunks: 250 } };
  }
  if (url === "/jurimetria/cobertura-mg-jec") {
    return {
      data: {
        documentos: 40,
        chunks: 90,
        documentos_indexados: 36,
        documentos_aprovados: 30,
        pct_fonte_validada_explicita: 75,
        ultima_atualizacao: "2026-08-08T12:00:00Z",
        colecoes: [],
      },
    };
  }
  if (url.startsWith("/jurimetria/interno/benchmarks")) {
    return {
      data: {
        fonte: "base interna",
        tribunal: new URLSearchParams(url.split("?")[1]).get("tribunal"),
        tempo_tramitacao: {
          media_dias: 120,
          mediana_dias: 100,
          total_processos: 8,
        },
      },
    };
  }
  if (url.startsWith("/jurimetria/interno/analise-prospectiva")) {
    return {
      data: {
        taxa_historica_favoravel: 62.5,
        amostra: 16,
        decididos: 16,
        acordos: 3,
        classe_filtrada: false,
        aviso: "Histórico interno; não é previsão.",
      },
    };
  }
  return { data: {} };
}

beforeEach(() => {
  getMock.mockReset();
  getMock.mockImplementation((url: string) => Promise.resolve(resposta(url)));
});

describe("Jurimetria — verdade da fonte", () => {
  it("renderiza fonte interna, total real e cobertura sem anunciar benchmark externo", async () => {
    render(<Jurimetria />);

    await waitFor(() => {
      expect(screen.getByText("Histórico Interno por Tribunal")).toBeTruthy();
    });

    expect(getMock).toHaveBeenCalledWith("/jurimetria/interno/stats");
    expect(getMock).toHaveBeenCalledWith("/jurimetria/cobertura-rag");
    expect(getMock).toHaveBeenCalledWith("/jurimetria/cobertura-mg-jec");
    expect(
      getMock.mock.calls.some(([url]) =>
        String(url).startsWith("/jurimetria/interno/benchmarks?tribunal=TJMG"),
      ),
    ).toBe(true);

    expect(screen.getByText("123")).toBeTruthy();
    expect(screen.getByText("casos com tribunal informado")).toBeTruthy();
    expect(
      screen.getByText("Cobertura Real do Conhecimento da IA"),
    ).toBeTruthy();
    expect(screen.getByText("100")).toBeTruthy();
    expect(screen.getByText("250")).toBeTruthy();
    expect(screen.getByText("40")).toBeTruthy();
    expect(screen.getByText("90")).toBeTruthy();
    expect(screen.getByText("75%")).toBeTruthy();
    expect(screen.getByText(/não são DataJud\/STJ/i)).toBeTruthy();
    expect(screen.getByText("Classe TPU (somente referência)")).toBeTruthy();
    expect(
      screen.getByPlaceholderText("Opcional — não filtra a base atual"),
    ).toBeTruthy();
  });

  it("aciona a análise prospectiva canônica e mostra a taxa histórica", async () => {
    render(<Jurimetria />);

    const botao = await screen.findByRole("button", {
      name: "Calcular histórico",
    });
    fireEvent.click(botao);

    await waitFor(() => {
      expect(
        getMock.mock.calls.some(([url]) =>
          String(url).startsWith(
            "/jurimetria/interno/analise-prospectiva?classe=&tribunal=TJMG&dias_estimados=365",
          ),
        ),
      ).toBe(true);
    });

    expect(await screen.findByText("62.5%")).toBeTruthy();
    expect(screen.getByText("Taxa histórica favorável")).toBeTruthy();
  });

  it("ignora resposta antiga quando o tribunal muda antes da requisição anterior terminar", async () => {
    let resolveTjmg: ((value: unknown) => void) | undefined;
    let resolveStj: ((value: unknown) => void) | undefined;

    getMock.mockImplementation((url: string) => {
      if (url === "/jurimetria/interno/benchmarks?tribunal=TJMG") {
        return new Promise((resolve) => {
          resolveTjmg = resolve;
        });
      }
      if (url === "/jurimetria/interno/benchmarks?tribunal=STJ") {
        return new Promise((resolve) => {
          resolveStj = resolve;
        });
      }
      return Promise.resolve(resposta(url));
    });

    render(<Jurimetria />);
    await screen.findByText("Histórico Interno por Tribunal");

    fireEvent.click(screen.getByRole("button", { name: "STJ" }));
    await waitFor(() => expect(resolveStj).toBeDefined());

    resolveStj?.({
      data: {
        fonte: "base interna",
        tempo_tramitacao: {
          media_dias: 45,
          mediana_dias: 40,
          total_processos: 9,
        },
      },
    });
    await waitFor(() => expect(screen.getByText("45d")).toBeTruthy());

    // A resposta mais lenta do TJMG chega depois e não pode sobrescrever o STJ.
    resolveTjmg?.({
      data: {
        fonte: "base interna",
        tempo_tramitacao: {
          media_dias: 999,
          mediana_dias: 999,
          total_processos: 99,
        },
      },
    });

    await waitFor(() => {
      expect(screen.getByText("45d")).toBeTruthy();
      expect(screen.queryByText("999d")).toBeNull();
    });
  });

  it("relaciona o recorte ao RAG, teses canônicas e skills existentes", async () => {
    getMock.mockImplementation((url: string, config?: any) => {
      if (url === "/rag/buscar") {
        return Promise.resolve({
          data: {
            query: "TJMG consumidor negativação",
            modo: "semantica",
            pipeline: "hibrida_governada",
            resultados: [
              {
                chunk_id: "c1",
                titulo: "Precedente TJMG",
                tribunal: "TJMG",
                categoria: "jurisprudencia",
                fonte: "fonte oficial",
                conteudo: "Trecho relacionado ao assunto pesquisado.",
              },
            ],
          },
        });
      }
      if (url === "/jurimetria/por-tese" && config?.params) {
        return Promise.resolve({
          data: [
            {
              id: "t1",
              titulo: "Negativação indevida",
              area_juridica: "consumidor",
              tribunal: "TJMG",
              decididos: 12,
              taxa_sucesso: 0.75,
              intervalo_confianca_95: {
                inferior: 0.4677,
                superior: 0.9111,
              },
            },
          ],
        });
      }
      if (url === "/ai/core/skills") {
        return Promise.resolve({
          data: [
            {
              nome: "ramo_consumidor",
              finalidade: "Método de Direito do Consumidor",
              riscos: "alto",
            },
            {
              nome: "modulo_jurimetria",
              finalidade: "Método do módulo de jurimetria",
              riscos: "médio",
            },
          ],
        });
      }
      return Promise.resolve(resposta(url));
    });

    render(<Jurimetria />);

    fireEvent.change(
      await screen.findByPlaceholderText(
        "Área: consumidor, civil, trabalhista...",
      ),
      { target: { value: "consumidor" } },
    );
    fireEvent.change(
      screen.getByPlaceholderText("Assunto: negativação indevida..."),
      { target: { value: "negativação" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Relacionar evidências" }),
    );

    expect(await screen.findByText("Precedente TJMG")).toBeTruthy();
    expect(screen.getByText("Negativação indevida")).toBeTruthy();
    expect(screen.getByText("ramo_consumidor")).toBeTruthy();
    expect(screen.getByText("modulo_jurimetria")).toBeTruthy();
    expect(screen.getByText(/taxa histórica 75.0%/i)).toBeTruthy();
  });

});
