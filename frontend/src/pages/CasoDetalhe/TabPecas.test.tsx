// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

vi.mock("../Pecas", () => ({
  default: () => (
    <div data-testid="workspace-pecas">Workspace completo de Peças</div>
  ),
}));
vi.mock("../../components/PecaGeneratorModal", () => ({ default: () => null }));

import TabPecas from "./TabPecas";

describe("TabPecas — workspace único", () => {
  afterEach(cleanup);

  it("reutiliza o workspace completo de Peças em vez de manter implementação paralela", () => {
    // A aba lê `?acao=produzir` da URL para abrir o gerador já no contexto do
    // caso — por isso precisa de Router mesmo sem navegar.
    render(
      <MemoryRouter>
        <TabPecas caseId="case-1" />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("workspace-pecas").textContent).toContain(
      "Workspace completo de Peças",
    );
    expect(screen.queryByText(/Abrir no módulo Peças/i)).toBeNull();
  });
});
