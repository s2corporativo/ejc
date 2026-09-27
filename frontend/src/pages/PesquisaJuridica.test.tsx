// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

const pesquisarMock = vi.fn();
const verificarMock = vi.fn();

vi.mock("../services/legalResearch", () => ({
  pesquisarFontesJuridicas: (...args: unknown[]) => pesquisarMock(...args),
  verificarCitacoesJuridicas: (...args: unknown[]) => verificarMock(...args),
}));

import PesquisaJuridica from "./PesquisaJuridica";

afterEach(() => {
  cleanup();
  pesquisarMock.mockReset();
  verificarMock.mockReset();
});

describe("PesquisaJuridica — P0 Inteligência Jurídica", () => {
  it("pesquisa no corpus governado e mostra a fonte recuperada", async () => {
    pesquisarMock.mockResolvedValue({
      query: "dano moral",
      modo: "semantica",
      pipeline: "hibrida_governada",
      resultados: [
        {
          chunk_id: "c1",
          titulo: "Precedente STJ",
          categoria: "jurisprudencia",
          tribunal: "STJ",
          fonte: "https://www.stj.jus.br/",
          confianca: "alta",
          conteudo: "Trecho recuperado da base governada.",
          similarity: 0.91,
        },
      ],
    });

    render(<PesquisaJuridica />);

    fireEvent.change(screen.getByLabelText("Consulta jurídica"), {
      target: { value: "dano moral" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Pesquisar/i }));

    await waitFor(() =>
      expect(pesquisarMock).toHaveBeenCalledWith("dano moral", 10),
    );
    expect(await screen.findByText("Precedente STJ")).toBeTruthy();
    expect(screen.getByText(/Trecho recuperado/)).toBeTruthy();
    expect(screen.getByText(/91% relevância/)).toBeTruthy();
  });

  it("valida citações com DataJud somente quando o usuário opta", async () => {
    verificarMock.mockResolvedValue({
      total: 1,
      confirmadas: 1,
      nao_encontradas: 0,
      score: 100,
      aviso: "Conferir inteiro teor.",
      avisos: ["Conferir inteiro teor."],
      citacoes: [
        {
          citacao: "0000000-00.2026.8.13.0000",
          tipo: "cnj",
          encontrada: true,
          status: "verificada",
          tribunal: "TJMG",
          fonte_verificacao: "DataJud",
        },
      ],
    });

    render(<PesquisaJuridica />);

    fireEvent.change(
      screen.getByPlaceholderText(
        /Cole aqui o trecho com números de processos/i,
      ),
      { target: { value: "Processo 0000000-00.2026.8.13.0000" } },
    );
    fireEvent.click(
      screen.getByLabelText(/Confirmar números CNJ também no DataJud/i),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /Verificar citações/i }),
    );

    await waitFor(() =>
      expect(verificarMock).toHaveBeenCalledWith(
        "Processo 0000000-00.2026.8.13.0000",
        true,
      ),
    );
    expect(await screen.findByText("Verificada")).toBeTruthy();
    expect(screen.getByText("100%")).toBeTruthy();
    expect(
      screen.getByText(/Fonte de verificação:/).closest("p")?.textContent,
    ).toContain("DataJud");
  });
});
