// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";

vi.mock("../stores/caseContext", () => {
  const state = {
    caso: {
      id: "case-1",
      titulo: "Caso Teste",
      cliente: "Cliente X",
      numero_processo: null,
      proxima_acao: "Protocolar manifestação",
      proxima_acao_prazo: "2026-09-05T12:00:00-03:00",
    },
    ativar: vi.fn(),
    sair: vi.fn(),
  };
  return {
    useCaseContext: (selector: (s: typeof state) => unknown) => selector(state),
  };
});

import CaseContextBar from "./CaseContextBar";

afterEach(cleanup);

describe("CaseContextBar — cinco destinos canônicos do modo caso", () => {
  it("exibe exatamente os rótulos Visão/Atividades/Documentos/Estratégia/Financeiro", () => {
    render(
      <MemoryRouter initialEntries={["/casos/case-1?tab=resumo"]}>
        <CaseContextBar />
      </MemoryRouter>,
    );

    const nav = screen.getByRole("navigation", {
      name: "Navegação principal do caso",
    });
    const rotulos = within(nav)
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(rotulos).toEqual([
      "Visão",
      "Atividades",
      "Documentos",
      "Estratégia",
      "Financeiro",
    ]);
  });

  it("mantém a próxima ação visível em qualquer superfície do caso", () => {
    render(
      <MemoryRouter initialEntries={["/casos/case-1?tab=documentos"]}>
        <CaseContextBar />
      </MemoryRouter>,
    );

    expect(screen.getByText("Protocolar manifestação")).toBeTruthy();
    expect(screen.getByText("05/09/2026")).toBeTruthy();
  });

  it("aponta cada destino para a aba padrão da seção", () => {
    render(
      <MemoryRouter initialEntries={["/casos/case-1?tab=resumo"]}>
        <CaseContextBar />
      </MemoryRouter>,
    );

    const nav = screen.getByRole("navigation", {
      name: "Navegação principal do caso",
    });
    const hrefs = within(nav)
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));
    expect(hrefs).toEqual([
      "/casos/case-1?tab=resumo",
      "/casos/case-1?tab=timeline",
      "/casos/case-1?tab=documentos",
      "/casos/case-1?tab=teses",
      "/casos/case-1?tab=financeiro",
    ]);
  });

  it("marca Visão como ativa na raiz do caso (sem ?tab)", () => {
    render(
      <MemoryRouter initialEntries={["/casos/case-1"]}>
        <CaseContextBar />
      </MemoryRouter>,
    );

    const visao = screen.getByRole("link", { name: "Visão" });
    expect(visao.getAttribute("aria-current")).toBe("page");
  });
});
