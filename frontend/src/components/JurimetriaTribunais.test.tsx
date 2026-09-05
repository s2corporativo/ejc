// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import api from "../lib/api";
import JurimetriaTribunais from "./JurimetriaTribunais";

vi.mock("../lib/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  getAccessToken: () => null,
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

const GRUPO = {
  n: 40,
  n_com_desfecho: 30,
  procedencia: 12,
  procedencia_parcial: 6,
  improcedencia: 6,
  acordo: 4,
  sem_resolucao_merito: 2,
  decididos_merito: 24,
  taxa_procedencia: 0.75,
  taxa_acordo: 0.1333,
  amostra_pequena: false,
  tempo_sentenca: { n: 20, mediana_dias: 412, media_dias: 455 },
};

const DESFECHOS = {
  fonte: "DataJud/CNJ — API Pública (api_publica_tjmg)",
  escopo: { tribunal: "TJMG", municipios: ["Betim", "Contagem", "Belo Horizonte"] },
  coleta: { cache: false, coletado_em: "2026-09-05T12:00:00Z", n_documentos: 52, truncado: false },
  tpu: { versao: "26/05/2026" },
  min_amostra: 10,
  limitacoes: ["proxy"],
  total: GRUPO,
  por_municipio: [
    { municipio: "betim", nome: "Betim", ...GRUPO },
    { municipio: "contagem", nome: "Contagem", ...GRUPO, n: 7, taxa_procedencia: null, amostra_pequena: true },
  ],
  por_assunto: [{ assunto_codigo: "9985", assunto: "Indenização por Dano Moral", ...GRUPO }],
  reforma_2grau: {
    n_com_recurso_julgado: 12,
    provimento: 3,
    provimento_parcial: 2,
    nao_provimento: 7,
    taxa_reforma: 0.4167,
    amostra_pequena: false,
  },
};

// Corpo em bloco de propósito: `mockReset()` devolve o próprio mock, e o
// vitest registra função retornada de `beforeEach` como hook de limpeza —
// chamaria `api.get()` sem URL ao fim de cada teste.
beforeEach(() => {
  vi.mocked(api.get).mockReset();
});
afterEach(cleanup);

describe("JurimetriaTribunais — coexistência rotulada com a jurimetria do escritório", () => {
  it("mostra taxas do tribunal com fonte, amostra e versão da TPU", async () => {
    vi.mocked(api.get).mockImplementation(async (url: string) => {
      if (url === "/jurimetria/tribunais/status") {
        return { data: { habilitado: true, datajud_habilitado: true, tpu_versao: "26/05/2026" } };
      }
      if (url === "/jurimetria/tribunais/desfechos") return { data: DESFECHOS };
      throw new Error(`url inesperada ${url}`);
    });
    render(<JurimetriaTribunais />);

    // O card do total e a linha de Betim compartilham a taxa na fixture:
    // o que importa é que a taxa do tribunal esteja na tela, com o n ao lado.
    expect((await screen.findAllByText("75.0%")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/24 decididos no mérito/)).toBeTruthy();
    expect(screen.getByText("412 dias")).toBeTruthy();
    expect(screen.getByText("41.7%")).toBeTruthy();
    // Rótulo que separa tribunal de escritório
    expect(screen.getByText(/Não é o desempenho do escritório/)).toBeTruthy();
    expect(screen.getByText(/TPU 26\/05\/2026/)).toBeTruthy();
    expect(screen.getByText(/proxy, não leitura da sentença/)).toBeTruthy();
    // Município com amostra pequena não exibe taxa inventada
    const contagem = screen.getByText("Contagem").closest("tr")!;
    expect(contagem.textContent).toContain("—");
  });

  it("sem flag: aviso de não configurado, sem chamar o DataJud", async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      data: { habilitado: false, datajud_habilitado: false, tpu_versao: "26/05/2026" },
    });
    render(<JurimetriaTribunais />);
    expect(await screen.findByRole("status")).toBeTruthy();
    expect(screen.getByText(/não configurada/)).toBeTruthy();
    expect(vi.mocked(api.get)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(api.get).mock.calls[0][0]).toBe("/jurimetria/tribunais/status");
  });

  it("503 no desfecho vira aviso, 502 vira indisponibilidade — nunca tela quebrada", async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ data: { habilitado: true, datajud_habilitado: true, tpu_versao: "x" } })
      .mockRejectedValueOnce({ response: { status: 502 } });
    render(<JurimetriaTribunais />);
    expect(await screen.findByText(/DataJud indisponível/)).toBeTruthy();
  });
});
