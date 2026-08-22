import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BancoNacionalTeses from "./BancoNacionalTeses";
import { listarTesesNacionais } from "../lib/legalThesisBank";

vi.mock("../lib/legalThesisBank", () => ({
  listarTesesNacionais: vi.fn(),
  obterTeseNacional: vi.fn(),
}));

const consultar = vi.mocked(listarTesesNacionais);

const tese = {
  id: "tese-1",
  chave_canonica: "consumidor-fraude-pix",
  titulo: "Responsabilidade por fraude PIX ligada ao risco da atividade bancária",
  area: "Consumidor",
  subarea: "Bancário",
  tema: "Fraude bancária",
  tipo: "material",
  lado: "ataque" as const,
  tese_principal: "A análise depende da relação jurídica e da prova da operação contestada.",
  fundamento_resumido: "Fonte oficial validada e revisão humana registrada.",
  pressupostos: [],
  fatos_necessarios: [],
  elementos_demonstrar: ["operação contestada"],
  fatos_impeditivos: [],
  excecoes: [],
  fundamentacao_legal: [],
  estrategia: { quando_utilizar: "Quando os fatos forem compatíveis com o risco da atividade." },
  provas_necessarias: ["extrato"],
  documentos_necessarios: [],
  riscos: [],
  score_forca: 82,
  status: "validada",
  versao: 1,
  vigente: true,
  recomendavel: true,
  origem: "coleta",
  criada_em: "2026-08-22T00:00:00Z",
  revisada_em: "2026-08-22T00:00:00Z",
};

describe("BancoNacionalTeses", () => {
  beforeEach(() => {
    consultar.mockReset();
  });

  it("explica por que registros não validados não aparecem como recomendação", async () => {
    consultar.mockResolvedValue({ total: 0, limit: 50, offset: 0, items: [] });

    render(<BancoNacionalTeses />);

    expect(await screen.findByText("Banco em preparação curatorial")).toBeTruthy();
    expect(
      screen.getByText(/Registros não validados permanecem fora da recomendação automática/),
    ).toBeTruthy();
  });

  it("renderiza a tese validada e envia a busca digitada ao backend", async () => {
    consultar.mockResolvedValue({ total: 1, limit: 50, offset: 0, items: [tese] });

    render(<BancoNacionalTeses />);
    expect(await screen.findByText(tese.titulo)).toBeTruthy();

    const search = screen.getByRole("textbox", { name: "Pesquisar teses jurídicas" });
    fireEvent.change(search, { target: { value: "fraude PIX" } });

    await waitFor(() => {
      expect(consultar).toHaveBeenCalledWith(
        expect.objectContaining({ busca: "fraude PIX", limit: 50 }),
      );
    });
  });
});
