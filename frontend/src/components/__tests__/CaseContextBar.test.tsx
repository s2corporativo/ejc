import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

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

  it("expõe cinco destinos canônicos do workspace do caso", () => {
    renderBar("/casos/case-1?tab=documentos");

    expect(
      screen.getByRole("link", { name: "Visão" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=resumo");
    expect(
      screen.getByRole("link", { name: "Atividades" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=timeline");
    expect(
      screen.getByRole("link", { name: "Arquivos" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=documentos");
    expect(
      screen.getByRole("link", { name: "Estratégia" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=teses");
    expect(
      screen.getByRole("link", { name: "Financeiro" }).getAttribute("href"),
    ).toBe("/casos/case-1?tab=financeiro");
    expect(
      screen.getByRole("link", { name: "Arquivos" }).getAttribute("aria-current"),
    ).toBe("page");
  });

  it("marca somente Estratégia como ativa na rota irmã Sala de Guerra", async () => {
    renderBar("/casos/case-1/sala-de-guerra");

    expect(
      screen
        .getByRole("link", { name: "Estratégia" })
        .getAttribute("aria-current"),
    ).toBe("page");
    expect(
      screen.getByRole("link", { name: "Visão" }).getAttribute("aria-current"),
    ).toBeNull();
    await waitFor(() => expect(mocks.ativar).toHaveBeenCalledWith("case-1"));
  });

  it("mantém a saída explícita do modo caso", () => {
    renderBar("/casos/case-1");

    fireEvent.click(screen.getByRole("button", { name: "Sair do modo caso" }));
    expect(mocks.sair).toHaveBeenCalledTimes(1);
  });
});
