// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { OrquestradorVisao } from "../lib/api";

const { visaoOrquestrador, avancarOrquestrador } = vi.hoisted(() => ({
  visaoOrquestrador: vi.fn(),
  avancarOrquestrador: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
  visaoOrquestrador,
  avancarOrquestrador,
}));

vi.mock("./Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import OrquestradorPanel from "./OrquestradorPanel";

const visao: OrquestradorVisao = {
  case_id: "caso-1",
  estado: "compreensao",
  estado_rotulo: "Compreensão dos fatos",
  estados: [
    "entrada",
    "compreensao",
    "classificacao",
    "validacao_processual",
    "estrategia",
    "contratacao",
    "producao",
    "revisao",
    "protocolo",
    "acompanhamento",
  ],
  proximo_passo: {
    estado: "compreensao",
    estado_rotulo: "Compreensão dos fatos",
    passo_recomendado:
      "Revisar e aprovar o snapshot de inteligência (fixa área/rito) — ato humano do advogado.",
    acoes_disponiveis: [
      {
        acao: "aprovar_snapshot",
        metodo: "POST",
        endpoint: "/cases/caso-1/inteligencia/{snapshot_id}/aprovar",
        payload_esperado: {},
        executavel_via_orquestrador: false,
      },
      {
        acao: "analisar_caso",
        metodo: "POST",
        endpoint: "/intake/casos/caso-1/analise-completa",
        payload_esperado: { texto: "opcional (string)" },
        executavel_via_orquestrador: true,
      },
    ],
    pendencias_bloqueantes: [
      {
        tipo: "aprovacao_humana",
        detalhe: "Snapshot de inteligência ainda não aprovado.",
        endpoint: "/cases/caso-1/inteligencia/{snapshot_id}/aprovar",
      },
    ],
  },
  jornada: [
    { etapa: "documentos_lidos", rotulo: "Documentos lidos", status: "concluida" },
    {
      etapa: "area_confirmada",
      rotulo: "Área confirmada pelo advogado",
      status: "bloqueada",
    },
    { etapa: "prazo_calculado", rotulo: "Prazo calculado", status: "pendente" },
  ],
  linha_do_tempo: [
    {
      versao: 1,
      origem: "intake",
      estado: "compreensao",
      resumo: "Análise completa do intake",
      congelado: false,
      criado_em: "2026-07-10T12:00:00Z",
    },
  ],
};

describe("OrquestradorPanel", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    visaoOrquestrador.mockReset();
    avancarOrquestrador.mockReset();
    visaoOrquestrador.mockResolvedValue(visao);
    avancarOrquestrador.mockResolvedValue({
      executado: true,
      acao: "analisar_caso",
      estado_anterior: "compreensao",
      estado: "compreensao",
      resultado: {},
    });
  });

  function renderPanel() {
    return render(
      <MemoryRouter>
        <OrquestradorPanel caseId="caso-1" />
      </MemoryRouter>,
    );
  }

  it("mostra estado atual, jornada, pendências e linha do tempo", async () => {
    renderPanel();

    expect(await screen.findByText("Compreensão dos fatos")).toBeTruthy();
    expect(
      screen.getByText(/Revisar e aprovar o snapshot de inteligência/),
    ).toBeTruthy();
    expect(screen.getByText("Documentos lidos")).toBeTruthy();
    expect(screen.getByText("Área confirmada pelo advogado")).toBeTruthy();
    expect(
      screen.getByText("Snapshot de inteligência ainda não aprovado."),
    ).toBeTruthy();
    expect(screen.getByText("Análise completa do intake")).toBeTruthy();
    expect(visaoOrquestrador).toHaveBeenCalledWith("caso-1");
  });

  it("ato de aprovação humana não é executável direto e aponta o fluxo próprio", async () => {
    renderPanel();

    expect(await screen.findByText("Aprovar snapshot de inteligência")).toBeTruthy();
    const desabilitado = screen.getByRole("button", {
      name: "Execução direta indisponível",
    }) as HTMLButtonElement;
    expect(desabilitado.disabled).toBe(true);
    expect(screen.getByText("Abrir jornada do caso")).toBeTruthy();
    expect(
      screen.getByText("Aprovação do advogado — abre o fluxo próprio."),
    ).toBeTruthy();
  });

  it("executa ação via /avancar após confirmação no modal", async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "Executar" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Executar agora" }),
    );

    await waitFor(() => {
      expect(avancarOrquestrador).toHaveBeenCalledWith(
        "caso-1",
        "analisar_caso",
        {},
      );
    });
    // Recarrega a visão depois da transição.
    await waitFor(() => expect(visaoOrquestrador).toHaveBeenCalledTimes(2));
  });

  it("exibe o detalhe estruturado de um 422 do /avancar", async () => {
    avancarOrquestrador.mockRejectedValue({
      response: {
        status: 422,
        data: {
          detail: {
            mensagem: "Parâmetros inválidos para a ação 'analisar_caso'",
            erros: [{ campo: "texto", erro: "valor inválido" }],
          },
        },
      },
    });
    renderPanel();

    fireEvent.click(await screen.findByRole("button", { name: "Executar" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Executar agora" }),
    );

    expect(
      await screen.findByText(
        "Parâmetros inválidos para a ação 'analisar_caso'",
      ),
    ).toBeTruthy();
    expect(await screen.findByText("texto: valor inválido")).toBeTruthy();
  });
});
