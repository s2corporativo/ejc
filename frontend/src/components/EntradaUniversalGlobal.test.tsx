// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useNavigate } from "react-router";

vi.mock("../stores/auth", () => ({
  useAuth: (selector: (state: { user: { role: string } }) => unknown) =>
    selector({ user: { role: "advogado" } }),
}));

vi.mock("./EntradaUniversalDocumentos", () => ({
  default: () => (
    <div data-testid="entrada-documentos">Entrada documentos</div>
  ),
}));

import EntradaUniversalGlobal from "./EntradaUniversalGlobal";

function ControleRota() {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate("/")}>
      Ir para dashboard
    </button>
  );
}

afterEach(() => cleanup());

describe("EntradaUniversalGlobal", () => {
  it("fecha e remove o modal quando a navegação retorna ao dashboard", async () => {
    render(
      <MemoryRouter initialEntries={["/documentos"]}>
        <EntradaUniversalGlobal />
        <ControleRota />
      </MemoryRouter>,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Abrir Entrada Universal de Documentos",
      }),
    );
    expect(
      screen.getByText("Entrada Universal de Documentos"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Ir para dashboard" }));

    await waitFor(() => {
      expect(
        screen.queryByText("Entrada Universal de Documentos"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", {
          name: "Abrir Entrada Universal de Documentos",
        }),
      ).not.toBeInTheDocument();
    });
  });
});
