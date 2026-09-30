import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

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

describe("CaseContextBar", () => {
  beforeEach(() => {
    mocks.ativar.mockClear();
    mocks.sair.mockClear();
  });

  it("expõe o fluxo jurídico canônico do caso", () => {
    renderBar("/casos/case-1?tab=provas");

    expect(
      screen.getByRole("link", { name: "Fatos" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=resumo");
    expect(
      screen.getByRole("link", { name: "Provas" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=provas");
    expect(
      screen.getByRole("link", { name: "Teses" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=teses");
    expect(
      screen.getByRole("link", { name: "Estratégia" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=dossie");
    expect(
      screen.getByRole("link", { name: "Peça" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=pecas");
    expect(
      screen.getByRole("link", { name: "Revisão" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=pecas#revisao");
    expect(
      screen.getByRole("link", { name: "Ajuizamento" }).getAttribute("href"),
    ).toBe("/ajuizamento?caso=case-1");
    expect(
      screen.getByRole("link", { name: "Provas" }).getAttribute("aria-current"),
    ).toBe("step");
  });

  it("mantém a saída explícita do modo caso", () => {
    renderBar("/casos/case-1");

    fireEvent.click(screen.getByRole("button", { name: "Sair do modo caso" }));
    expect(mocks.sair).toHaveBeenCalledTimes(1);
  });
});
