import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";

const mocks = vi.hoisted(() => ({
  ativar: vi.fn().mockResolvedValue(undefined),
  sair: vi.fn(),
}));

vi.mock("../../stores/caseContext", () => ({
  useCaseContext: (selector: (state: unknown) => unknown) =>
    selector({
      caso: {
        id: "case-1",
        titulo: "Ação de cobrança",
        cliente: "Cliente Teste",
        numero_processo: "0000000-00.2026.8.13.0000",
        proxima_acao: "Protocolar manifestação",
        proxima_acao_prazo: "2026-09-05T12:00:00-03:00",
      },
      ativar: mocks.ativar,
      sair: mocks.sair,
    }),
}));

import CaseContextBar from "../CaseContextBar";

function renderBar(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <CaseContextBar />
    </MemoryRouter>,
  );
}

describe("CaseContextBar — navegação simplificada do caso", () => {
  beforeEach(() => {
    mocks.ativar.mockClear();
    mocks.sair.mockClear();
  });

  it("expõe somente as cinco áreas canônicas do workspace", () => {
    renderBar("/casos/case-1?tab=provas");

    const nav = screen.getByRole("navigation", { name: "Áreas do caso" });
    expect(
      within(nav)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual([
      "Visão",
      "Atividades",
      "Documentos",
      "Estratégia",
      "Financeiro",
    ]);

    expect(
      screen.getByRole("link", { name: "Visão" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=resumo");
    expect(
      screen.getByRole("link", { name: "Atividades" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=timeline");
    expect(
      screen.getByRole("link", { name: "Documentos" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=documentos");
    expect(
      screen.getByRole("link", { name: "Estratégia" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=teses");
    expect(
      screen.getByRole("link", { name: "Financeiro" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=financeiro");
  });

  it("marca a seção correspondente à subaba ativa", () => {
    renderBar("/casos/case-1?tab=provas");

    expect(
      screen
        .getByRole("link", { name: "Documentos" })
        .getAttribute("aria-current"),
    ).toBe("page");
  });

  it("mantém a próxima ação visível sem replicar a jornada", () => {
    renderBar("/casos/case-1?tab=documentos");

    expect(screen.getByText("Protocolar manifestação")).toBeTruthy();
    expect(screen.getByText("05/09/2026")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Ajuizamento" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Revisão" })).toBeNull();
  });

  it("mantém a saída explícita do modo caso", () => {
    renderBar("/casos/case-1");

    fireEvent.click(screen.getByRole("button", { name: "Sair do modo caso" }));
    expect(mocks.sair).toHaveBeenCalledTimes(1);
  });

  it("sair do modo caso dentro de /casos/:id volta à lista (sem workspace órfão de áreas)", () => {
    render(
      <MemoryRouter initialEntries={["/casos/case-1?tab=timeline"]}>
        <CaseContextBar />
        <Routes>
          <Route path="/casos" element={<p>lista de casos</p>} />
          <Route path="/casos/:id" element={<p>workspace do caso</p>} />
          <Route path="/ajuizamento" element={<p>ajuizamento</p>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Sair do modo caso" }));
    expect(screen.getByText("lista de casos")).toBeTruthy();
  });

  it("sair do modo caso fora de /casos/:id não navega", () => {
    render(
      <MemoryRouter initialEntries={["/ajuizamento?caso=case-1"]}>
        <CaseContextBar />
        <Routes>
          <Route path="/casos" element={<p>lista de casos</p>} />
          <Route path="/ajuizamento" element={<p>ajuizamento</p>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Sair do modo caso" }));
    expect(mocks.sair).toHaveBeenCalledTimes(1);
    expect(screen.getByText("ajuizamento")).toBeTruthy();
  });
});
