// @vitest-environment jsdom
// Fase 1 do plano de simplificação — "O caso abre com a próxima ação":
//   • os cinco GROUPS da página batem com a barra canônica (config/caseNav);
//   • o deep-link legado ?tab=orquestrador redireciona para ?tab=resumo;
//   • entrar em /casos/:id mostra a próxima ação sem clique adicional.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";

vi.mock("../components/OrquestradorPanel", () => ({
  default: ({ caseId }: { caseId: string }) => (
    <div>PROXIMA_ACAO_ORQUESTRADOR:{caseId}</div>
  ),
}));
vi.mock("./CasoDetalhe/TabResumo", () => ({
  default: () => <div>DADOS_TAB_RESUMO</div>,
  AvisoCasoEncerrado: () => <div>AVISO_CASO_ENCERRADO</div>,
}));
vi.mock("../components/ContextualAIAssistant", () => ({
  default: () => null,
}));
vi.mock("../components/CaseBreadcrumb", () => ({
  default: () => null,
}));
vi.mock("../components/visual/BadgesAlerta", () => ({
  default: () => null,
}));

import api from "../lib/api";
import CasoDetalhe, { GROUPS, TABS } from "./CasoDetalhe";
import {
  CASE_NAV_SECTIONS,
  LEGACY_CASE_TAB_REDIRECTS,
} from "../config/caseNav";

function UrlProbe() {
  const { pathname, search } = useLocation();
  return <div>URL_ATUAL:{`${pathname}${search}`}</div>;
}

function renderCaso(entrada: string) {
  return render(
    <MemoryRouter initialEntries={[entrada]}>
      <Routes>
        <Route
          path="/casos/:id"
          element={
            <>
              <CasoDetalhe />
              <UrlProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("CasoDetalhe — GROUPS batem com a barra canônica", () => {
  it("usa exatamente os cinco rótulos de config/caseNav, na mesma ordem", () => {
    expect(GROUPS.map((g) => g.label)).toEqual(
      CASE_NAV_SECTIONS.map((s) => s.label),
    );
    expect(GROUPS.map((g) => g.label)).toEqual([
      "Visão",
      "Atividades",
      "Arquivos",
      "Estratégia",
      "Financeiro",
    ]);
  });

  it("agrupa as mesmas abas da barra, sem perder nenhuma aba do workspace", () => {
    // Página ↔ barra: cada seção agrupa exatamente as abas declaradas na
    // fonte canônica (nenhuma aba é filtrada por não existir em TABS).
    GROUPS.forEach((grupo, i) => {
      expect(grupo.tabs).toEqual(CASE_NAV_SECTIONS[i].tabs);
    });

    // Nenhuma aba/capacidade removida — só reagrupada: a união dos grupos
    // cobre todas as TABS, sem sobras nem duplicatas.
    const agrupadas = GROUPS.flatMap((g) => g.tabs);
    expect(new Set(agrupadas).size).toBe(agrupadas.length);
    expect([...agrupadas].sort()).toEqual(TABS.map((t) => t.key).sort());
  });

  it("não tem mais a aba orquestrador como destino próprio", () => {
    expect(TABS.some((t) => (t.key as string) === "orquestrador")).toBe(false);
    expect(LEGACY_CASE_TAB_REDIRECTS.orquestrador).toBe("resumo");
  });
});

describe("CasoDetalhe — a Visão abre com a próxima ação", () => {
  function mockCaso(status: string) {
    vi.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/cases/case-1") {
        return Promise.resolve({
          data: {
            id: "case-1",
            titulo: "Caso Teste",
            status,
            area: "civel",
          },
        });
      }
      return Promise.resolve({ data: [] });
    });
  }

  beforeEach(() => {
    mockCaso("ativo");
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("mostra a próxima ação do orquestrador sem clique adicional", async () => {
    renderCaso("/casos/case-1");

    expect(
      await screen.findByText("PROXIMA_ACAO_ORQUESTRADOR:case-1"),
    ).toBeTruthy();
    // Dados do caso ficam numa linha recolhível abaixo da próxima ação.
    expect(screen.getByRole("button", { name: /Dados do caso/ })).toBeTruthy();
  });

  it("caso encerrado: aviso de reabertura no topo e Dados do caso já aberto", async () => {
    mockCaso("encerrado");
    renderCaso("/casos/case-1");

    // Aviso + controle de reabrir em destaque, ANTES do painel do orquestrador.
    expect(await screen.findByText("AVISO_CASO_ENCERRADO")).toBeTruthy();
    expect(screen.getByText("PROXIMA_ACAO_ORQUESTRADOR:case-1")).toBeTruthy();
    // "Dados do caso" inicia expandido nesses status (conteúdo visível).
    const linha = screen.getByRole("button", { name: /Dados do caso/ });
    expect(linha.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("DADOS_TAB_RESUMO")).toBeTruthy();
  });

  it("redireciona o deep-link legado ?tab=orquestrador para ?tab=resumo", async () => {
    renderCaso("/casos/case-1?tab=orquestrador");

    // O conteúdo promovido continua acessível (sem 404, sem aba morta)...
    expect(
      await screen.findByText("PROXIMA_ACAO_ORQUESTRADOR:case-1"),
    ).toBeTruthy();
    // ...e a URL é normalizada para a aba nova.
    await waitFor(() => {
      expect(
        screen.getByText("URL_ATUAL:/casos/case-1?tab=resumo"),
      ).toBeTruthy();
    });
  });
});
