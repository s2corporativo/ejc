// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ModuleLifecycleOverride } from "../stores/moduleLifecycle";

// Store mockado com estado mutável entre os casos — evita chamada real de API
// no load() e permite alternar loaded=false/true.
const estado = {
  settings: {} as Record<string, ModuleLifecycleOverride>,
  loaded: false,
  load: vi.fn(async () => {}),
};

vi.mock("../stores/moduleLifecycle", () => ({
  useModuleLifecycleStore: () => estado,
}));

import ModuleLifecycleGate from "./ModuleLifecycleGate";

afterEach(() => {
  cleanup();
  estado.loaded = false;
  estado.settings = {};
});

function renderGate() {
  return render(
    <MemoryRouter initialEntries={["/casos"]}>
      <ModuleLifecycleGate>
        <div data-testid="pagina">conteúdo do módulo</div>
      </ModuleLifecycleGate>
    </MemoryRouter>,
  );
}

describe("ModuleLifecycleGate — FLX-023 (não montar página antes do lifecycle)", () => {
  it("NÃO renderiza os children enquanto o lifecycle não carregou", () => {
    renderGate();
    // Placeholder neutro no lugar da página: nenhum request do módulo dispara
    // antes do gate saber se ele está habilitado.
    expect(screen.queryByTestId("pagina")).toBeNull();
    expect(estado.load).toHaveBeenCalled();
  });

  it("renderiza os children após loaded=true (fail-open do store preservado)", () => {
    estado.loaded = true;
    renderGate();
    expect(screen.getByTestId("pagina")).toBeTruthy();
  });
});
