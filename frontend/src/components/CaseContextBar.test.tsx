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

describe("CaseContextBar — fluxo jurídico do caso", () => {
  it("expõe o mesmo fluxo visual do dashboard", () => {
    render(
      <MemoryRouter initialEntries={["/casos/case-1?tab=resumo"]}>
        <CaseContextBar />
      </MemoryRouter>,
    );

    const nav = screen.getByRole("navigation", {
      name: "Fluxo jurídico do caso",
    });
    const rotulos = within(nav)
      .getAllByRole("link")
      .map((link) => link.textContent?.replace(/^\d{2}/, ""));
    expect(rotulos).toEqual([
      "Fatos",
      "Provas",
      "Teses",
      "Estratégia",
      "Peça",
      "Revisão",
      "Ajuizamento",
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

  it("aponta o fluxo para as superfícies reais do caso", () => {
    render(
      <MemoryRouter initialEntries={["/casos/case-1?tab=resumo"]}>
        <CaseContextBar />
      </MemoryRouter>,
    );

    const nav = screen.getByRole("navigation", {
      name: "Fluxo jurídico do caso",
    });
    const hrefs = within(nav)
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));
    expect(hrefs).toEqual([
      "/casos/case-1?tab=resumo",
      "/casos/case-1?tab=provas",
      "/casos/case-1?tab=teses",
      "/casos/case-1?tab=dossie",
      "/casos/case-1?tab=pecas",
      "/casos/case-1?tab=pecas#revisao",
      "/ajuizamento?caso=case-1",
    ]);
  });

  it("marca Fatos como etapa ativa na raiz do caso", () => {
    render(
      <MemoryRouter initialEntries={["/casos/case-1"]}>
        <CaseContextBar />
      </MemoryRouter>,
    );

    const fatos = screen.getByRole("link", { name: "Fatos" });
    expect(fatos.getAttribute("aria-current")).toBe("step");
  });
});
