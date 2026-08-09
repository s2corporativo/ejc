// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import CaseFilterChip from "./CaseFilterChip";

describe("CaseFilterChip — contexto obrigatório do Caso", () => {
  afterEach(cleanup);

  it("não permite remover o contexto dentro de /casos/:id", () => {
    const remover = vi.fn();
    render(
      <MemoryRouter initialEntries={["/casos/caso-1?tab=pecas"]}>
        <CaseFilterChip nome="Caso Um" onRemove={remover} />
      </MemoryRouter>,
    );

    expect(screen.getByText(/Caso ativo: Caso Um/)).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Remover filtro de caso" }),
    ).toBeNull();
    expect(remover).not.toHaveBeenCalled();
  });

  it("continua removível em uma fila global", () => {
    const remover = vi.fn();
    render(
      <MemoryRouter initialEntries={["/pecas?caso=caso-1"]}>
        <CaseFilterChip nome="Caso Um" onRemove={remover} />
      </MemoryRouter>,
    );

    const botao = screen.getByRole("button", {
      name: "Remover filtro de caso",
    });
    fireEvent.click(botao);
    expect(remover).toHaveBeenCalledTimes(1);
  });
});
