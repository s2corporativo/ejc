// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

let papelAtual = "advogado";

vi.mock("../stores/auth", () => ({
  useAuth: (selector: (state: { user: { role: string } }) => unknown) =>
    selector({ user: { role: papelAtual } }),
}));

vi.mock("./DashboardUltra", () => ({
  default: () => <div data-testid="dashboard-ultra">Dashboard Ultra</div>,
}));

import Dashboard from "./Dashboard";

afterEach(() => cleanup());

function renderizar() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  );
}

describe("Dashboard — acesso PJe", () => {
  it("exibe intimações para papel jurídico autorizado", () => {
    papelAtual = "advogado";
    renderizar();

    const link = screen.getByRole("link", { name: /Abrir intimações/i });
    expect(link.getAttribute("href")).toBe("/atividades?tipo=intimacao");
    expect(screen.getByTestId("dashboard-ultra")).toBeTruthy();
  });

  it("não renderiza o acesso PJe para papel não autorizado", () => {
    papelAtual = "cliente_externo";
    renderizar();

    expect(
      screen.queryByRole("link", { name: /Abrir intimações/i }),
    ).toBeNull();
    expect(screen.getByTestId("dashboard-ultra")).toBeTruthy();
  });
});
