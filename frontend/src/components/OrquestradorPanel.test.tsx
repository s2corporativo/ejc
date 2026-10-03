// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
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

const authState = vi.hoisted(() => ({
  user: { role: "advogado" } as { role: string } | null,
}));
vi.mock("../stores/auth", () => ({
  useAuth: () => authState,
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
    {
      etapa: "documentos_lidos",
      rotulo: "Base fática registrada",
      status: "concluida",
    },
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

function abrirDetalhes() {
  fireEvent.click(screen.getByText("Ver detalhes"));
}

describe("OrquestradorPanel — próxima ação simplificada", () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    authState.user = { role: "advogado" };
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

  function renderPanel(status = "aberto") {
    return render(
      <MemoryRouter>
        <OrquestradorPanel caseId="caso-1" casoStatus={status} />
      </MemoryRouter>,
    );
  }

  it("mostra somente próxima ação e pendências na superfície principal", async () => {
    renderPanel();

    expect(await screen.findByText("Próxima ação")).toBeTruthy();
    expect(screen.queryByText("Aberto")).toBeNull();
    expect(
      screen.getByText(/Revisar e aprovar o snapshot de inteligência/),
    ).toBeTruthy();
    expect(
      screen.getByText("Snapshot de inteligência ainda não aprovado."),
    ).toBeTruthy();

    // A jornada completa continua disponível, mas recolhida em "Ver detalhes";
    // a timeline não compete mais com a próxima ação na superfície principal.
    expect(screen.getByText("Ver detalhes")).toBeTruthy();
    expect(screen.getByText("Base fática registrada")).toBeTruthy();
    expect(screen.queryByText("Análise completa do intake")).toBeNull();
    expect(visaoOrquestrador).toHaveBeenCalledWith("caso-1");
  });

  it("distingue etapa em andamento de etapa pendente na jornada detalhada", async () => {
    visaoOrquestrador.mockResolvedValue({
      ...visao,
      jornada: [
        ...visao.jornada,
        {
          etapa: "area_sugerida",
          rotulo: "Área sugerida",
          status: "em_andamento",
        },
        {
          etapa: "area_confirmada",
          rotulo: "Área confirmada pelo advogado",
          status: "pendente",
        },
      ],
    });
    renderPanel();

    expect(await screen.findByText("Área sugerida")).toBeTruthy();
    expect(screen.getByText("Em andamento")).toBeTruthy();
    expect(screen.getAllByText("Pendente")).toHaveLength(1);
  });

  it("ato de aprovação humana aponta direto para a superfície canônica", async () => {
    renderPanel();
    await screen.findByText("Próxima ação");
    abrirDetalhes();

    expect(screen.getByText("Aprovar snapshot de inteligência")).toBeTruthy();
    expect(screen.getByText("Revisar inteligência do caso")).toBeTruthy();
    expect(screen.getByText("Exige decisão ou aprovação humana.")).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Execução direta indisponível" }),
    ).toBeNull();
  });

  it("executa ação via /avancar após confirmação no modal", async () => {
    renderPanel();
    await screen.findByText("Próxima ação");
    abrirDetalhes();

    fireEvent.click(screen.getByRole("button", { name: "Executar" }));
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
    await waitFor(() => expect(visaoOrquestrador).toHaveBeenCalledTimes(2));
  });

  it("caso encerrado/arquivado fica em leitura e bloqueia execução", async () => {
    for (const status of ["encerrado", "arquivado"]) {
      renderPanel(status);
      expect(
        (await screen.findAllByText(/Revisar e aprovar o snapshot/)).length,
      ).toBeGreaterThan(0);
      expect(screen.getByText("Caso em modo leitura")).toBeTruthy();
      abrirDetalhes();

      const botao = screen.getByRole("button", {
        name: "Executar",
      }) as HTMLButtonElement;
      expect(botao.disabled).toBe(true);
      expect(botao.getAttribute("title")).toBe(
        "Reabra o caso para executar ações",
      );
      cleanup();
    }
  });

  it("role abaixo de advogado mantém leitura e bloqueia execução", async () => {
    for (const role of ["advogado_auxiliar", "estagiario", "secretaria"]) {
      authState.user = { role };
      renderPanel();
      await screen.findByText("Próxima ação");
      abrirDetalhes();

      const botao = screen.getByRole("button", {
        name: "Executar",
      }) as HTMLButtonElement;
      expect(botao.disabled).toBe(true);
      expect(botao.getAttribute("title")).toBe(
        "Ação disponível para advogados",
      );
      cleanup();
    }
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
    await screen.findByText("Próxima ação");
    abrirDetalhes();

    fireEvent.click(screen.getByRole("button", { name: "Executar" }));
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
