// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../stores/caseContext", () => {
  const state = {
    caso: {
      id: "case-1",
      titulo: "Caso Teste",
      cliente: "Cliente X",
      numero_processo: null,
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
  it("exibe exatamente os rótulos Visão/Atividades/Arquivos/Estratégia/Financeiro", () => {
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
      "Arquivos",
      "Estratégia",
      "Financeiro",
    ]);
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
