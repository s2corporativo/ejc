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

function resposta(url: string) {
  if (url === "/jurimetria/desfechos") {
    return { data: { total_encerrados: 0, por_resultado: [], lessons_learned: [] } };
  }
  if (url === "/jurimetria/overview") {
    return { data: { taxa_sucesso_geral: 0.5 } };
  }
  if (url === "/jurimetria/por-area") return { data: [] };
  if (url === "/jurimetria/por-tribunal") return { data: [] };
  if (url === "/jurimetria/por-tese") return { data: [] };
  if (url === "/jurimetria/interno/stats") {
    return { data: { fonte: "base interna", por_tribunal: [{ tribunal: "TJMG", total: 12 }] } };
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
        tempo_tramitacao: { media_dias: 120, mediana_dias: 100, total_processos: 8 },
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
  it("renderiza fonte interna e cobertura real sem anunciar benchmark externo", async () => {
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

    expect(screen.getByText("Cobertura Real do Conhecimento da IA")).toBeTruthy();
    expect(screen.getByText("100")).toBeTruthy();
    expect(screen.getByText("250")).toBeTruthy();
    expect(screen.getByText("40")).toBeTruthy();
    expect(screen.getByText("90")).toBeTruthy();
    expect(screen.getByText("75%")).toBeTruthy();
    expect(screen.getByText(/não são DataJud\/STJ/i)).toBeTruthy();
    expect(screen.getByText("Classe TPU (somente referência)")).toBeTruthy();
    expect(screen.getByPlaceholderText("Opcional — não filtra a base atual")).toBeTruthy();
  });

  it("aciona a análise prospectiva canônica e mostra a taxa histórica", async () => {
    render(<Jurimetria />);

    const botao = await screen.findByRole("button", { name: "Calcular histórico" });
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
});
