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
  intervalo_confianca_95_procedencia: {
    inferior: 0.551,
    superior: 0.879,
    nivel: 0.95,
    metodo: "wilson",
  },
  taxa_acordo: 0.1333,
  intervalo_confianca_95_acordo: {
    inferior: 0.053,
    superior: 0.296,
    nivel: 0.95,
    metodo: "wilson",
  },
  amostra_pequena: false,
  tempo_sentenca: { n: 20, mediana_dias: 412, media_dias: 455 },
};

const DESFECHOS = {
  fonte: "DataJud/CNJ — API Pública (api_publica_tjmg)",
  escopo: {
    tribunal: "TJMG",
    municipios: ["Betim", "Contagem", "Belo Horizonte"],
  },
  coleta: {
    cache: false,
    coletado_em: "2026-09-05T12:00:00Z",
    n_documentos: 52,
    truncado: false,
  },
  tpu: { versao: "26/05/2026" },
  min_amostra: 10,
  limitacoes: ["proxy"],
  total: GRUPO,
  por_municipio: [
    { municipio: "betim", nome: "Betim", ...GRUPO },
    {
      municipio: "contagem",
      nome: "Contagem",
      ...GRUPO,
      n: 7,
      taxa_procedencia: null,
      amostra_pequena: true,
    },
  ],
  por_assunto: [
    {
      assunto_codigo: "9985",
      assunto: "Indenização por Dano Moral",
      ...GRUPO,
    },
  ],
  reforma_2grau: {
    n_com_recurso_julgado: 12,
    provimento: 3,
    provimento_parcial: 2,
    nao_provimento: 7,
    taxa_reforma: 0.4167,
    intervalo_confianca_95_reforma: {
      inferior: 0.193,
      superior: 0.681,
      nivel: 0.95,
      metodo: "wilson",
    },
    amostra_pequena: false,
  },
  fontes_complementares: {
    jec_tjmg: {
      disponivel: true,
      fonte: "DataJud/CNJ — API Pública (api_publica_tjmg)",
      escopo: {
        tribunal: "TJMG",
        segmento: "Juizados Especiais / Turmas Recursais",
      },
      coleta: {
        cache: false,
        coletado_em: "2026-09-05T12:00:00Z",
        n_documentos: 14,
        derivado_sem_nova_consulta: true,
      },
      total: { ...GRUPO, n: 14 },
    },
    trt3: {
      disponivel: true,
      fonte: "DataJud/CNJ — API Pública (api_publica_trt3)",
      escopo: { tribunal: "TRT3", regiao: "3ª Região — Minas Gerais" },
      coleta: {
        cache: false,
        coletado_em: "2026-09-05T12:00:00Z",
        n_documentos: 80,
      },
      total: { ...GRUPO, n: 80 },
    },
  },
};

beforeEach(() => {
  vi.mocked(api.get).mockReset();
});
afterEach(cleanup);

describe("JurimetriaTribunais — coexistência rotulada com a jurimetria do escritório", () => {
  it("mostra TJMG, JEC e TRT3 com fonte, amostra e versão da TPU", async () => {
    vi.mocked(api.get).mockImplementation(async (url: string) => {
      if (url === "/jurimetria/tribunais/status") {
        return {
          data: {
            habilitado: true,
            datajud_habilitado: true,
            snapshot_habilitado: true,
            tpu_versao: "26/05/2026",
          },
        };
      }
      if (url === "/jurimetria/tribunais/desfechos") {
        return { data: DESFECHOS };
      }
      if (url === "/jurimetria/tribunais/historico") {
        return {
          data: {
            items: [
              {
                id: "s1",
                tribunal: "TJMG",
                n_documentos: 52,
                amostra_truncada: false,
                coletado_em: "2026-09-20T12:00:00Z",
              },
            ],
          },
        };
      }
      throw new Error(`url inesperada ${url}`);
    });
    render(<JurimetriaTribunais />);

    expect((await screen.findAllByText("75.0%")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/24 decididos no mérito/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("412 dias")).toBeTruthy();
    expect(screen.getByText("41.7%")).toBeTruthy();
    expect(screen.getAllByText(/IC95% 55\.1%–87\.9%/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/IC95% 19\.3%–68\.1%/)).toBeTruthy();
    expect(screen.getByText(/Não é o desempenho do escritório/)).toBeTruthy();
    expect(screen.getByText(/TPU 26\/05\/2026/)).toBeTruthy();
    expect(screen.getByText(/proxy, não leitura da sentença/)).toBeTruthy();
    expect(screen.getByText(/Juizados Especiais \/ Turmas Recursais — TJMG/)).toBeTruthy();
    expect(screen.getByText(/Justiça do Trabalho — TRT3\/MG/)).toBeTruthy();
    expect(screen.getByText(/n=14/)).toBeTruthy();
    expect(screen.getByText(/n=80/)).toBeTruthy();
    expect(screen.getByText(/Histórico agregado: 1 snapshot/)).toBeTruthy();

    const contagem = screen.getByText("Contagem").closest("tr")!;
    expect(contagem.textContent).toContain("—");
  });

  it("sem flag: aviso de não configurado, sem chamar o DataJud", async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      data: {
        habilitado: false,
        datajud_habilitado: false,
        tpu_versao: "26/05/2026",
      },
    });
    render(<JurimetriaTribunais />);
    expect(await screen.findByRole("status")).toBeTruthy();
    expect(screen.getByText(/não configurada/)).toBeTruthy();
    expect(vi.mocked(api.get)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(api.get).mock.calls[0][0]).toBe(
      "/jurimetria/tribunais/status",
    );
  });

  it("502 no desfecho vira indisponibilidade — nunca tela quebrada", async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({
        data: {
          habilitado: true,
          datajud_habilitado: true,
          tpu_versao: "x",
        },
      })
      .mockRejectedValueOnce({ response: { status: 502 } });
    render(<JurimetriaTribunais />);
    expect(await screen.findByText(/DataJud indisponível/)).toBeTruthy();
  });
});
