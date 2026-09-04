// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import type { ModuleLifecycleOverride } from "../stores/moduleLifecycle";

vi.mock("../lib/api", () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock("../stores/auth", () => ({
  useAuth: (selector: (state: { user: unknown }) => unknown) =>
    selector({ user: { id: "u1", role: "superadmin", full_name: "Titular" } }),
}));

// Painéis pesados do hub não fazem parte do que está sob teste aqui.
vi.mock("../components/DefesasRevisoesPanel", () => ({
  default: () => null,
}));
vi.mock("../components/RevisaoBancariaDeterministica", () => ({
  default: () => null,
}));

import Ferramentas from "./Ferramentas";
import { useModuleLifecycleStore } from "../stores/moduleLifecycle";

function override(
  moduleKey: string,
  patch: Partial<ModuleLifecycleOverride>,
): ModuleLifecycleOverride {
  return {
    module_key: moduleKey,
    enabled: true,
    menu_visible: true,
    status: "active",
    ...patch,
  };
}

function montar(settings: Record<string, ModuleLifecycleOverride>) {
  useModuleLifecycleStore.setState({ settings, loaded: true });
  render(
    <MemoryRouter>
      <Ferramentas />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
  useModuleLifecycleStore.setState({ settings: {}, loaded: true });
});

afterEach(() => {
  cleanup();
  useModuleLifecycleStore.setState({ settings: {}, loaded: false });
});

describe("Mais Ferramentas — ciclo de vida dos módulos", () => {
  it("não oferece cartão de módulo desativado pela administração", () => {
    montar({
      radar: override("radar", { enabled: false, status: "disabled" }),
    });

    // Sem o filtro, o cartão aparecia e o clique caía no ModuleLifecycleGate.
    expect(screen.queryByText("Radar")).toBeNull();
    expect(screen.getByText("Auditoria")).toBeTruthy();
  });

  it("mantém os módulos ocultos do menu — é para isso que o hub existe", () => {
    montar({});

    expect(screen.getByText("Radar")).toBeTruthy();
    expect(screen.getByText("Ajuda")).toBeTruthy();
    expect(screen.getByText("Cadastro Manual")).toBeTruthy();
  });

  it("um módulo fora do menu por configuração ainda aparece no catálogo", () => {
    // menu_visible=false tira do menu lateral, mas a rota continua acessível:
    // esconder o cartão deixaria o módulo sem nenhum ponto de entrada.
    montar({ lixeira: override("lixeira", { menu_visible: false }) });

    expect(screen.getByText("Lixeira")).toBeTruthy();
  });
});
