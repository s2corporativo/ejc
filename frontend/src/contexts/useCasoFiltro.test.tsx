// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { useCasoFiltro } from "./useCasoFiltro";

vi.mock("../stores/caseContext", () => ({
  useCaseContext: (selector: (state: unknown) => unknown) =>
    selector({ caso: null }),
}));

vi.mock("../lib/api", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

function Probe() {
  const { casoFiltro, removerFiltro } = useCasoFiltro();
  return (
    <div>
      <span data-testid="caso">{casoFiltro || "sem-caso"}</span>
      <button onClick={removerFiltro}>remover</button>
    </div>
  );
}

describe("useCasoFiltro — contexto pela rota", () => {
  afterEach(cleanup);

  it("deriva imediatamente o caso de /casos/:id", () => {
    render(
      <MemoryRouter initialEntries={["/casos/case-123?tab=pecas"]}>
        <Probe />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("caso").textContent).toBe("case-123");
  });

  it("faz o caso da rota vencer uma query de outro caso", () => {
    render(
      <MemoryRouter initialEntries={["/casos/caso-a?caso=caso-b&tab=pecas"]}>
        <Probe />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("caso").textContent).toBe("caso-a");
  });

  it("não derruba a tela quando o segmento possui escape percentual inválido", () => {
    render(
      <MemoryRouter initialEntries={["/casos/%E0%A4?tab=pecas"]}>
        <Probe />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("caso").textContent).toBe("sem-caso");
  });

  it("não trata /casos/novo como contexto de caso", () => {
    render(
      <MemoryRouter initialEntries={["/casos/novo"]}>
        <Probe />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("caso").textContent).toBe("sem-caso");
  });
});
