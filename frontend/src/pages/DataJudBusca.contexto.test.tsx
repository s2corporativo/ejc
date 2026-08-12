// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import api from "../lib/api";
import DataJudBusca from "./DataJudBusca";

describe("DataJudBusca — contexto do caso", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("prefere o número do deep-link e sincroniza explicitamente o caso informado", async () => {
    vi.spyOn(api, "get").mockResolvedValue({
      data: {
        numero: "1234567-89.2023.8.26.0000",
        tribunal: "TJSP",
        movimentos: [],
        partes: [],
      },
    });
    const post = vi.spyOn(api, "post").mockResolvedValue({
      data: { synced: 4 },
    });

    render(
      <MemoryRouter
        initialEntries={[
          "/datajud?numero=1234567-89.2023.8.26.0000&caso=case-1",
        ]}
      >
        <DataJudBusca />
      </MemoryRouter>,
    );

    const campo = screen.getByPlaceholderText(/0000000-00\.0000\.0\.00\.0000/i);
    expect((campo as HTMLInputElement).value).toBe("1234567-89.2023.8.26.0000");

    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
    await screen.findByText("TJSP");

    fireEvent.click(
      screen.getByRole("button", { name: /Sincronizar com este caso/ }),
    );

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith("/datajud/cases/case-1/sync");
    });
    expect(await screen.findByText(/4 movimentos atualizados/)).toBeTruthy();
  });

  it("renderiza falha de sincronização como erro e não como mensagem de sucesso", async () => {
    vi.spyOn(api, "get").mockResolvedValue({
      data: {
        numero: "1234567-89.2023.8.26.0000",
        tribunal: "TJSP",
        movimentos: [],
        partes: [],
      },
    });
    vi.spyOn(api, "post").mockRejectedValue({
      response: { data: { detail: "Falha controlada de sincronização" } },
    });

    render(
      <MemoryRouter
        initialEntries={[
          "/datajud?numero=1234567-89.2023.8.26.0000&caso=case-1",
        ]}
      >
        <DataJudBusca />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
    await screen.findByText("TJSP");
    fireEvent.click(
      screen.getByRole("button", { name: /Sincronizar com este caso/ }),
    );

    const erro = await screen.findByText("Falha controlada de sincronização");
    const erroEl = screen.getByText("Falha controlada de sincronização").closest("p");
    expect(erroEl?.className).toContain("text-danger-700");
    expect(screen.queryByText(/Sincronizado:/)).toBeNull();
  });
});
