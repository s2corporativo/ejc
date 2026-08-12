// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

vi.mock("../Pecas", () => ({
  default: () => <div data-testid="workspace-pecas">Workspace completo de Peças</div>,
}));

import TabPecas from "./TabPecas";

describe("TabPecas — workspace único", () => {
  afterEach(cleanup);

  it("reutiliza o workspace completo de Peças em vez de manter implementação paralela", () => {
    render(<TabPecas caseId="case-1" />);
    expect(screen.getByTestId("workspace-pecas").textContent).toContain(
      "Workspace completo de Peças",
    );
    expect(screen.queryByText(/Abrir no módulo Peças/i)).toBeNull();
  });
});
