import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";

const { get, post, remove } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  remove: vi.fn(),
}));

vi.mock("../../lib/api", () => ({
  default: { get, post, delete: remove },
}));

vi.mock("../../lib/areas", () => ({
  useAreas: () => [
    { slug: "civil", nome: "Cível" },
    { slug: "transito", nome: "Trânsito" },
    { slug: "licitacoes", nome: "Licitações" },
  ],
}));

vi.mock("../Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import CaseCommandDock from "../CaseCommandDock";

describe("CaseCommandDock", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    remove.mockReset();
    get.mockResolvedValue({
      data: { areas: [{ area: "civil", principal: true }] },
    });
    post.mockResolvedValue({ data: { ok: true } });
    remove.mockResolvedValue({ data: { ok: true } });
  });

  it("navega pelos MESMOS cinco destinos canônicos da barra do caso", () => {
    render(
      <MemoryRouter>
        <CaseCommandDock caseId="case-1" />
      </MemoryRouter>,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /Abrir ações simples/ }),
    );

    expect(screen.getByText("Modo simples")).toBeTruthy();
    // Fase 1: os destinos de navegação são exatamente os cinco rótulos
    // canônicos (config/caseNav) — os mesmos da CaseContextBar e da página.
    for (const rotulo of [
      "Visão",
      "Atividades",
      "Arquivos",
      "Estratégia",
      "Financeiro",
    ]) {
      expect(screen.getByText(rotulo)).toBeTruthy();
    }
    // "Peças" deixou de ser um sexto destino de navegação: virou ação de
    // produção, ao lado de Áreas do caso e Anexar documento.
    expect(screen.queryByText("Jornada e próxima ação")).toBeNull();
    expect(screen.getByRole("button", { name: /Peças do caso/ })).toBeTruthy();
  });

  it("usa a taxonomia canônica e vincula uma área ao caso", async () => {
    render(
      <MemoryRouter>
        <CaseCommandDock caseId="case-1" />
      </MemoryRouter>,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /Abrir ações simples/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Áreas do caso" }));

    expect(await screen.findByText("Cível")).toBeTruthy();
    const select = screen.getByRole("combobox");
    expect(screen.getByRole("option", { name: "Trânsito" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "Licitações" })).toBeTruthy();

    fireEvent.change(select, { target: { value: "transito" } });
    fireEvent.click(screen.getByRole("button", { name: "Adicionar" }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith("/cases/case-1/areas", {
        area: "transito",
      });
    });
  });

  it("expõe somente formatos aceitos pelo backend documental", () => {
    const { container } = render(
      <MemoryRouter>
        <CaseCommandDock caseId="case-1" />
      </MemoryRouter>,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /Abrir ações simples/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Anexar documento" }));

    const input = container.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement | null;
    expect(input).toBeTruthy();
    expect(input?.accept).toContain(".pdf");
    expect(input?.accept).toContain(".doc");
    expect(input?.accept).toContain(".txt");
    expect(input?.accept).toContain(".xml");
    expect(screen.getByRole("option", { name: "Prova" })).toBeTruthy();
  });
});
