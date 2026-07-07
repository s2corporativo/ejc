/**
 * Página 404 (item 2.4): rota desconhecida deve mostrar "não encontrado", não o
 * Dashboard silencioso. Teste de smoke do componente.
 *
 * Usa apenas matchers nativos do vitest (getByText já lança se não achar), para
 * não depender de @testing-library/jest-dom — mantendo o setup do repo enxuto.
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
    // getByText lança se o elemento não existir; a asserção torna a intenção explícita.
    expect(screen.getByText("404")).toBeTruthy();
    expect(screen.getByText(/não encontrada/i)).toBeTruthy();
  });
});
