import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DashboardIA from "./DashboardIA";

const getMock = vi.fn();

vi.mock("../lib/api", () => ({
  default: { get: (...args: unknown[]) => getMock(...args) },
}));

beforeEach(() => getMock.mockReset());

function erroHttp(status: number, detail?: unknown) {
  return Object.assign(new Error(`HTTP ${status}`), {
    response: { status, data: { detail } },
  });
}

describe("Saúde da IA (E4)", () => {
  it("erro de carga vira ErrorState com retry — não painel de zeros", async () => {
    getMock.mockRejectedValueOnce(erroHttp(500, "Traceback provider x"));
    render(<DashboardIA />);
    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent(/Não foi possível carregar a saúde da IA/);
    // detail técnico não vaza
    expect(alerta).not.toHaveTextContent(/Traceback/);
    expect(screen.queryByText("Chamadas")).toBeNull();

    getMock.mockResolvedValueOnce({
      data: { total_chamadas: 12, custo_total_brl: 3.5, por_modelo: {} },
    });
    fireEvent.click(screen.getByRole("button", { name: /Tentar novamente/ }));
    await waitFor(() => expect(screen.getByText("Chamadas")).toBeTruthy());
    expect(screen.getByText("12")).toBeTruthy();
    expect(getMock).toHaveBeenCalledTimes(2);
  });

  it("403 mostra mensagem de permissão", async () => {
    getMock.mockRejectedValueOnce(erroHttp(403, "Not enough permissions"));
    render(<DashboardIA />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /não tem permissão/i,
    );
  });
});
