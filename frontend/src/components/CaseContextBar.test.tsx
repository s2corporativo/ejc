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

describe("CaseContextBar — navegação principal simplificada", () => {
  it("expõe somente as cinco áreas canônicas", () => {
    render(
      <MemoryRouter initialEntries={["/casos/case-1?tab=resumo"]}>
        <CaseContextBar />
      </MemoryRouter>,
    );

    const nav = screen.getByRole("navigation", { name: "Áreas do caso" });
    expect(
      within(nav)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["Visão", "Atividades", "Documentos", "Estratégia", "Financeiro"]);
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

  it("aponta as cinco áreas para as superfícies canônicas", () => {
    render(
      <MemoryRouter initialEntries={["/casos/case-1?tab=resumo"]}>
        <CaseContextBar />
      </MemoryRouter>,
    );

    const nav = screen.getByRole("navigation", { name: "Áreas do caso" });
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

  it("marca Documentos pela subaba Provas sem criar outra navegação", () => {
    render(
      <MemoryRouter initialEntries={["/casos/case-1?tab=provas"]}>
        <CaseContextBar />
      </MemoryRouter>,
    );

    expect(
      screen
        .getByRole("link", { name: "Documentos" })
        .getAttribute("aria-current"),
    ).toBe("page");
    expect(screen.queryByRole("link", { name: "Provas" })).toBeNull();
  });
});
