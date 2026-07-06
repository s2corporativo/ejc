/**
 * Página 404 (item 2.4): rota desconhecida deve mostrar "não encontrado", não o
 * Dashboard silencioso. Teste de smoke do componente.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import NotFound from "../NotFound";

describe("NotFound", () => {
  it("exibe 404 e a mensagem de não encontrado", () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>,
    );
    expect(screen.getByText("404")).toBeInTheDocument();
    expect(screen.getByText(/não encontrada/i)).toBeInTheDocument();
  });
});
