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

  it("expõe apenas ações contextuais sem repetir a navegação principal", () => {
    render(
      <MemoryRouter>
        <CaseCommandDock caseId="case-1" />
      </MemoryRouter>,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /Abrir ações simples/ }),
    );

    expect(screen.getByText("Modo simples")).toBeTruthy();
    for (const rotulo of [
      "Visão",
      "Atividades",
      "Documentos",
      "Estratégia",
      "Financeiro",
    ]) {
      expect(screen.queryByText(rotulo)).toBeNull();
    }
    expect(screen.getByRole("button", { name: /Produzir peça/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Fila de peças/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Áreas do caso" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Anexar documento" }),
    ).toBeTruthy();
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
