// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const get = vi.fn();
const setTheme = vi.fn();

vi.mock("../lib/api", () => ({
  default: { get },
}));

vi.mock("../stores/theme", () => ({
  THEME_LABELS: {
    light: "Claro",
    dark: "Escuro",
    system: "Sistema",
  },
  useThemeStore: () => ({ theme: "light", setTheme }),
}));

import ThemeSelector from "./ThemeSelector";

beforeEach(() => {
  get.mockReset();
  setTheme.mockReset();
});

afterEach(cleanup);

describe("ThemeSelector no Dashboard", () => {
  it("exibe alerta quando o backend informa blocos degradados", async () => {
    get.mockResolvedValue({
      data: { degradado: ["casos", "financeiro"] },
    });

    render(
      <MemoryRouter initialEntries={["/"]}>
        <ThemeSelector />
      </MemoryRouter>,
    );

    const alerta = await screen.findByRole("alert");
    expect(alerta.textContent).toContain("Dados temporariamente indisponíveis");
    expect(alerta.textContent).toContain("Casos");
    expect(alerta.textContent).toContain("Financeiro");
    expect(get).toHaveBeenCalledWith("/dashboard/");
  });

  it("exibe indisponibilidade quando a chamada completa do Dashboard falha", async () => {
    get.mockRejectedValue(new Error("offline"));

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <ThemeSelector />
      </MemoryRouter>,
    );

    const alerta = await screen.findByRole("alert");
    expect(alerta.textContent).toContain("Painel temporariamente indisponível");
  });

  it("não consulta o Dashboard fora da página inicial", async () => {
    render(
      <MemoryRouter initialEntries={["/configuracoes"]}>
        <ThemeSelector />
      </MemoryRouter>,
    );

    await waitFor(() => expect(get).not.toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
