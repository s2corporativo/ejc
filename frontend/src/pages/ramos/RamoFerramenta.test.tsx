// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import api from "../../lib/api";
import {
  MENSAGEM_DEMONSTRATIVO_INDISPONIVEL,
  MENSAGEM_DEMONSTRATIVO_SEM_PERMISSAO,
} from "../../lib/iaErro";
import { _resetPecasCapacidadesCache } from "../../lib/pecasCapacidades";
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

/** Capacidade anunciada por `GET /pecas/meta` nesta instalação de teste. */
type Capacidade = "liberada" | "bloqueada" | "meta-indisponivel";

function mockarGet(capacidade: Capacidade) {
  getMock.mockImplementation((url: string) => {
    if (url === "/pecas/meta") {
      return capacidade === "meta-indisponivel"
        ? Promise.reject(new Error("falha de rede"))
        : (Promise.resolve({
            data: {
              capacidades: {
                demonstrativo_calculadora: capacidade === "liberada",
              },
            },
          }) as never);
    }
    return Promise.resolve({ data: resultado }) as never;
  });
}

/** Renderiza, calcula e devolve o botão de exportação — SEM clicar nele. */
async function calcular(capacidade: Capacidade = "liberada") {
  mockarGet(capacidade);
  render(
    <MemoryRouter>
      <RamoFerramenta f={ferramenta} />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Calcular" }));
  return await screen.findByRole("button", { name: /Gerar demonstrativo/ });
}

async function calcularEExportar(capacidade: Capacidade = "liberada") {
  const botao = await calcular(capacidade);
  fireEvent.click(botao);
  return botao;
}

beforeEach(() => {
  vi.clearAllMocks();
  _resetPecasCapacidadesCache();
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

  it("usa o caso contextual validado ao gerar demonstrativo", async () => {
    mockarGet("liberada");
    postMock.mockResolvedValueOnce({ data: { id: "peca-contextual" } } as never);

    render(
      <MemoryRouter>
        <RamoFerramenta
          f={ferramenta}
          caseContext={{ id: "case-contexto", titulo: "Caso Contextual" }}
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Calcular" }));
    const botao = await screen.findByRole("button", {
      name: /Gerar demonstrativo/,
    });
    fireEvent.click(botao);

    expect(postMock).toHaveBeenCalledWith(
      "/pecas/demonstrativo",
      expect.objectContaining({ case_id: "case-contexto" }),
    );
    expect(
      await screen.findByText(/vinculado ao caso "Caso Contextual"/),
    ).toBeTruthy();
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

// A capacidade `capacidades.demonstrativo_calculadora` de GET /pecas/meta
// existe para o advogado NÃO montar o cálculo inteiro e só então bater num
// botão que sempre falha. O 403 continua sendo rede de segurança, não a
// primeira linha de defesa.
describe("RamoFerramenta — capacidade anunciada por /pecas/meta", () => {
  it("desabilita o botão ANTES de qualquer clique quando a capacidade é false", async () => {
    const botao = await calcular("bloqueada");

    // Mensagem à vista, sem exigir hover: texto de apoio + tooltip.
    expect(
      await screen.findByText(MENSAGEM_DEMONSTRATIVO_INDISPONIVEL),
    ).toBeTruthy();
    expect((botao as HTMLButtonElement).disabled).toBe(true);
    expect(botao.getAttribute("title")).toBe(
      MENSAGEM_DEMONSTRATIVO_INDISPONIVEL,
    );
    // Nenhuma tentativa de exportação: o clique nem chega ao backend.
    fireEvent.click(botao);
    expect(postMock).not.toHaveBeenCalled();
    // A calculadora em si continua na tela — a trava é só da exportação.
    expect(screen.getByText(/Prazo Final/i)).toBeTruthy();
  });

  it("mantém o botão habilitado quando a capacidade é true", async () => {
    const botao = await calcular("liberada");

    expect((botao as HTMLButtonElement).disabled).toBe(false);
    expect(botao.getAttribute("title")).toBeNull();
    expect(screen.queryByText(MENSAGEM_DEMONSTRATIVO_INDISPONIVEL)).toBeNull();
    expect(getMock).toHaveBeenCalledWith("/pecas/meta");
  });

  it("degrada para o comportamento antigo quando /pecas/meta falha", async () => {
    postMock.mockRejectedValueOnce(
      erro403(
        "Exportação de demonstrativo bloqueada: as regras das calculadoras " +
          "estão em revisão (não homologadas).",
      ),
    );

    // Falha ao carregar a capacidade não trava a tela nem esconde a
    // calculadora: botão habilitado (fail-open).
    const botao = await calcular("meta-indisponivel");
    expect((botao as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByText(/Prazo Final/i)).toBeTruthy();

    // …e o 403 segue sendo tratado como antes.
    fireEvent.click(botao);
    expect(
      await screen.findByText(MENSAGEM_DEMONSTRATIVO_INDISPONIVEL),
    ).toBeTruthy();
    expect((botao as HTMLButtonElement).disabled).toBe(true);
  });
});
