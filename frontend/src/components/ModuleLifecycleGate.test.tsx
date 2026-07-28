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
  liberarPorTimeout: vi.fn(),
};

const TIMEOUT_MS = 8000;

vi.mock("../stores/moduleLifecycle", () => ({
  useModuleLifecycleStore: () => estado,
  MODULE_LIFECYCLE_TIMEOUT_MS: 8000,
}));

import ModuleLifecycleGate from "./ModuleLifecycleGate";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  estado.loaded = false;
  estado.settings = {};
  estado.load.mockClear();
  estado.liberarPorTimeout.mockClear();
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

  it("libera pelo fallback quando o request fica pendente além do teto", () => {
    vi.useFakeTimers();
    renderGate();
    expect(estado.liberarPorTimeout).not.toHaveBeenCalled();
    // Request nunca respondeu: o gate não pode segurar o <Outlet/> global.
    vi.advanceTimersByTime(TIMEOUT_MS);
    expect(estado.liberarPorTimeout).toHaveBeenCalledTimes(1);
    // Sem loop: passado o limite, nada mais é reagendado.
    vi.advanceTimersByTime(TIMEOUT_MS * 3);
    expect(estado.liberarPorTimeout).toHaveBeenCalledTimes(1);
  });

  it("não agenda fallback quando o lifecycle já carregou", () => {
    vi.useFakeTimers();
    estado.loaded = true;
    renderGate();
    vi.advanceTimersByTime(TIMEOUT_MS * 2);
    expect(estado.liberarPorTimeout).not.toHaveBeenCalled();
  });
});
