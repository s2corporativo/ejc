// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import api from "../../lib/api";
import type { Case } from "../../types";
import {
  AnaliseDocumentoArea,
  ComparadorBacen,
  modalidadeSelecionada,
} from "./RamoAnalise";

vi.mock("../../lib/api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const getMock = vi.mocked(api.get);
const postMock = vi.mocked(api.post);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ComparadorBacen", () => {
  it("não converte seleção vazia em índice zero", () => {
    const modalidades = [{ modalidade: "Crédito pessoal" }];
    expect(modalidadeSelecionada(modalidades, "")).toBeUndefined();
    expect(modalidadeSelecionada(modalidades, "0")).toBe(modalidades[0]);
  });

  it("exibe falha quando as modalidades não podem ser carregadas", async () => {
    getMock.mockRejectedValueOnce(new Error("indisponível"));

    render(<ComparadorBacen />);

    expect(
      await screen.findByText(/não foi possível carregar as modalidades do BACEN/i),
    ).toBeTruthy();
  });

  it("não consulta taxa média sem modalidade selecionada", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        periodo: "2026-07",
        modalidades: [
          { modalidade: "Crédito pessoal", segmento: "PESSOA FÍSICA" },
        ],
      },
    } as any);

    render(<ComparadorBacen />);
    await screen.findByText(/Crédito pessoal/);
    fireEvent.click(screen.getByRole("button", { name: "Comparar" }));

    expect(await screen.findByText("Selecione a modalidade.")).toBeTruthy();
    expect(getMock).toHaveBeenCalledTimes(1);
  });

  it("remove o resultado anterior quando a modalidade muda", async () => {
    getMock
      .mockResolvedValueOnce({
        data: {
          periodo: "2026-07",
          modalidades: [
            { modalidade: "Crédito pessoal", segmento: "PESSOA FÍSICA" },
            { modalidade: "Capital de giro", segmento: "PESSOA JURÍDICA" },
          ],
        },
      } as any)
      .mockResolvedValueOnce({
        data: {
          periodo: "2026-07",
          instituicoes: 12,
          ao_mes: { min: 1, media: 2, max: 3 },
        },
      } as any);

    render(<ComparadorBacen />);
    const [seletor] = await screen.findAllByRole("combobox");
    fireEvent.change(seletor, { target: { value: "0" } });
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Comparar" }));

    expect(
      await screen.findByText(/média retornada para a modalidade/i),
    ).toBeTruthy();
    fireEvent.change(seletor, { target: { value: "1" } });
    expect(screen.queryByText(/média retornada para a modalidade/i)).toBeNull();
  });
});

describe("AnaliseDocumentoArea", () => {
  it("impede POST duplicado ao salvar a mesma análise por clique repetido", async () => {
    let liberarMovimento: (() => void) | undefined;
    const movimentoPendente = new Promise<void>((resolve) => {
      liberarMovimento = resolve;
    });

    postMock.mockImplementation(async (url: string) => {
      if (url === "/analise-bancaria/contrato") {
        return {
          data: {
            resumo: "Resumo estruturado do documento",
            tarifas_encargos: [],
            clausulas_questionaveis: [],
          },
        } as any;
      }
      if (url.includes("/movimentos")) {
        await movimentoPendente;
        return { data: {} } as any;
      }
      return { data: {} } as any;
    });

    const caso = {
      id: "caso-1",
      titulo: "Caso de teste",
      numero_interno: "EJC-TESTE",
    } as Case;

    render(<AnaliseDocumentoArea area="bancario" casos={[caso]} />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "x".repeat(140) },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Analisar texto colado" }),
    );
    await screen.findByText("Resumo estruturado do documento");

    const [seletorCaso] = screen.getAllByRole("combobox");
    fireEvent.change(seletorCaso, { target: { value: "caso-1" } });
    const salvar = screen.getByRole("button", { name: "💾 Salvar no caso" });
    fireEvent.click(salvar);
    fireEvent.click(salvar);

    await waitFor(() => {
      const movimentos = postMock.mock.calls.filter(([url]) =>
        String(url).includes("/movimentos"),
      );
      expect(movimentos).toHaveLength(1);
    });

    liberarMovimento?.();
    expect(await screen.findByText(/análise salva no histórico/i)).toBeTruthy();
  });
});
