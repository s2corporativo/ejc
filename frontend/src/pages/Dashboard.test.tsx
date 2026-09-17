// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./DashboardUltra", () => ({
  default: () => <div data-testid="dashboard-ultra">Dashboard Ultra</div>,
}));

import Dashboard from "./Dashboard";

afterEach(() => cleanup());

describe("Dashboard — wrapper canônico do Início", () => {
  it("mantém um h1 acessível e delega a interface ao DashboardUltra", () => {
    render(<Dashboard />);

    expect(
      screen.getByRole("heading", {
        level: 1,
        name: /Entrada Única, ajuizamento, riscos de prazo e comunicações processuais/i,
      }),
    ).toBeTruthy();
    expect(screen.getByTestId("dashboard-ultra")).toBeTruthy();
  });

  it("não recria o banner PJe legado fora do dashboard canônico", () => {
    render(<Dashboard />);

    expect(screen.queryByRole("link", { name: /Abrir intimações/i })).toBeNull();
    expect(screen.queryByText(/PJe \/ Comunicações processuais/i)).toBeNull();
  });
});
