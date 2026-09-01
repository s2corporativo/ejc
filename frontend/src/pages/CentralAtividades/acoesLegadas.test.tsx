// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock("../../lib/api", () => ({
  default: {
    post,
    get: vi.fn(),
  },
}));

vi.mock("../../components/Toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

import { SimularPrazoModal } from "./acoesLegadas";


describe("SimularPrazoModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    post.mockResolvedValue({
      data: {
        data_vencimento: "2026-09-18",
        regime_calculo: "penal",
        modo: "CPP art. 798",
        resultado_preliminar: false,
        revisao_obrigatoria: false,
      },
    });
  });

  it("usa exclusivamente /deadlines/calcular com regime explícito", async () => {
    const { container } = render(
      <SimularPrazoModal open={true} onClose={vi.fn()} />,
    );

    const data = container.querySelector('input[type="date"]') as HTMLInputElement;
    expect(data).toBeTruthy();
    fireEvent.change(data, { target: { value: "2026-09-01" } });

    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "penal" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Simular" }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post).toHaveBeenCalledWith("/deadlines/calcular", {
      data_inicio: "2026-09-01",
      dias: 15,
      tipo: "processual",
      regime_calculo: "penal",
      tribunal: null,
      dobro: false,
      excecao_recesso_penal: false,
    });
    expect(post).not.toHaveBeenCalledWith(
      "/suspensoes/simular",
      expect.anything(),
    );
  });

  it("mostra aviso de conferência quando tribunal não é informado", () => {
    render(<SimularPrazoModal open={true} onClose={vi.fn()} />);
    expect(
      screen.getByText(/Tribunal não informado: feriados e suspensões locais/),
    ).toBeTruthy();
  });
});
