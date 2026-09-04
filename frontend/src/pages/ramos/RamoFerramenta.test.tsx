// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import api from "../../lib/api";
import {
  MENSAGEM_DEMONSTRATIVO_INDISPONIVEL,
  MENSAGEM_DEMONSTRATIVO_SEM_PERMISSAO,
} from "../../lib/iaErro";
import type { FerramentaConfig } from "./ramosConfig";
import RamoFerramenta from "./RamoFerramenta";

vi.mock("../../lib/api", () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock("../../stores/caseContext", () => ({
  useCaseContext: (selector: (state: { caso: null }) => unknown) =>
    selector({ caso: null }),
}));

const getMock = vi.mocked(api.get);
const postMock = vi.mocked(api.post);

// Calculadora homologada (`homologada` ausente = true): é exatamente o caso em
// que o botão ficava habilitado e o backend respondia 403 pela flag desligada.
const ferramenta: FerramentaConfig = {
  id: "prazos-contestacao",
  titulo: "Prazos de contestação",
  descricao: "Contagem de prazo",
  baseLegal: "CPC, art. 335",
  endpoint: "/civel/ferramentas/prazos-contestacao",
  campos: [{ nome: "data", label: "Data", tipo: "date" }],
};

const resultado = {
  prazo_final: "2026-10-01",
  fontes: ["CPC/2015"],
  vigencia_regra: "vigente desde 2016",
  versao_regra: "2026.1",
};

function erro403(detail: string) {
  return { response: { status: 403, data: { detail } } };
}

async function calcularEExportar() {
  getMock.mockResolvedValueOnce({ data: resultado } as never);
  render(
    <MemoryRouter>
      <RamoFerramenta f={ferramenta} />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Calcular" }));
  const botao = await screen.findByRole("button", {
    name: /Gerar demonstrativo/,
  });
  fireEvent.click(botao);
  return botao;
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("RamoFerramenta — exportação do demonstrativo", () => {
  it("degrada o 403 da trava de homologação em mensagem clara e trava o botão", async () => {
    postMock.mockRejectedValueOnce(
      erro403(
        "Exportação de demonstrativo bloqueada: as regras das calculadoras " +
          "estão em revisão (não homologadas — auditoria 2026-07-26).",
      ),
    );

    const botao = await calcularEExportar();

    expect(
      await screen.findByText(MENSAGEM_DEMONSTRATIVO_INDISPONIVEL),
    ).toBeTruthy();
    // Sem o texto cru do backend: nada de "auditoria 2026-07-26" na tela.
    expect(screen.queryByText(/auditoria 2026-07-26/)).toBeNull();
    // O advogado não fica batendo na mesma porta fechada.
    expect((botao as HTMLButtonElement).disabled).toBe(true);
  });

  it("distingue o 403 de permissão da trava de homologação", async () => {
    postMock.mockRejectedValueOnce(erro403("Acesso negado"));

    const botao = await calcularEExportar();

    expect(
      await screen.findByText(MENSAGEM_DEMONSTRATIVO_SEM_PERMISSAO),
    ).toBeTruthy();
    // Erro de papel não é bloqueio administrativo: o botão segue disponível.
    expect((botao as HTMLButtonElement).disabled).toBe(false);
  });

  it("confirma o salvamento quando a exportação está liberada", async () => {
    postMock.mockResolvedValueOnce({ data: { id: "peca-1" } } as never);

    const botao = await calcularEExportar();

    expect(await screen.findByText(/Salvo em Peças > Rascunhos/)).toBeTruthy();
    expect((botao as HTMLButtonElement).disabled).toBe(false);
    expect(postMock).toHaveBeenCalledWith(
      "/pecas/demonstrativo",
      expect.objectContaining({
        ferramenta: "/civel/ferramentas/prazos-contestacao",
        versao_regra: "2026.1",
      }),
    );
  });
});
