// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

// `acoesLegadas` importa a store de auth, que lê `getAccessToken()` já na
// avaliação do módulo. Um mock só com o default derruba o arquivo inteiro na
// coleta ("No 'getAccessToken' export is defined"), sem rodar teste nenhum.
vi.mock("../../lib/api", () => ({
  default: {
    post,
    get: vi.fn(),
  },
  getAccessToken: () => null,
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

vi.mock("../../components/Toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

import { PrazoSugeridoModal, SimularPrazoModal } from "./acoesLegadas";


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


describe("PrazoSugeridoModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    post.mockResolvedValue({
      data: {
        criado: true,
        data_prazo: "2026-09-22",
      },
    });
  });

  it("só aceita DJEN após informar os quatro marcos e regime", async () => {
    const onClose = vi.fn();
    const onResolvido = vi.fn();
    render(
      <PrazoSugeridoModal
        sugestao={{
          id: "com-1",
          titulo: "Intimação de teste",
          dados: {
            disponivel: false,
            case_id: "case-1",
            data_disponibilizacao: "2026-09-01",
            aviso: "Revisão necessária",
            prazo_sugerido_status: "nenhum",
          },
        }}
        onClose={onClose}
        onResolvido={onResolvido}
      />,
    );

    const aceitar = screen.getByRole("button", {
      name: "Cadastrar prazo revisado",
    }) as HTMLButtonElement;
    expect(aceitar.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Data de publicação"), {
      target: { value: "2026-09-02" },
    });
    fireEvent.change(screen.getByLabelText("Termo inicial"), {
      target: { value: "2026-09-03" },
    });
    fireEvent.change(screen.getByLabelText("Regime processual"), {
      target: { value: "civel" },
    });
    fireEvent.change(screen.getByLabelText("Vencimento final"), {
      target: { value: "2026-09-22" },
    });
    expect(aceitar.disabled).toBe(true);

    fireEvent.click(screen.getByLabelText("Confirmei a fonte oficial"));
    expect(aceitar.disabled).toBe(false);
    fireEvent.click(aceitar);

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        "/intimacoes/com-1/aceitar-prazo",
        {
          data_publicacao: "2026-09-02",
          termo_inicial: "2026-09-03",
          regime_calculo: "civel",
          data_prazo: "2026-09-22",
          confirmacao_fonte_oficial: true,
        },
      ),
    );
    await waitFor(() => expect(onResolvido).toHaveBeenCalledTimes(1));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("mantém bloqueio quando intimação não está vinculada a caso", () => {
    render(
      <PrazoSugeridoModal
        sugestao={{
          id: "com-sem-caso",
          titulo: "Intimação sem caso",
          dados: {
            disponivel: false,
            case_id: null,
            prazo_sugerido_status: "nenhum",
          },
        }}
        onClose={vi.fn()}
        onResolvido={vi.fn()}
      />,
    );
    expect(screen.getByText(/ainda não está vinculada a um caso/i)).toBeTruthy();
    const aceitar = screen.getByRole("button", {
      name: "Cadastrar prazo revisado",
    }) as HTMLButtonElement;
    expect(aceitar.disabled).toBe(true);
  });

  it("não envia quando a cronologia dos marcos é inválida", async () => {
    render(
      <PrazoSugeridoModal
        sugestao={{
          id: "com-crono",
          titulo: "Intimação cronologia",
          dados: {
            disponivel: false,
            case_id: "case-1",
            data_disponibilizacao: "2026-09-05",
            prazo_sugerido_status: "nenhum",
          },
        }}
        onClose={vi.fn()}
        onResolvido={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("Data de publicação"), {
      target: { value: "2026-09-04" },
    });
    fireEvent.change(screen.getByLabelText("Termo inicial"), {
      target: { value: "2026-09-06" },
    });
    fireEvent.change(screen.getByLabelText("Regime processual"), {
      target: { value: "civel" },
    });
    fireEvent.change(screen.getByLabelText("Vencimento final"), {
      target: { value: "2026-09-20" },
    });
    fireEvent.click(screen.getByLabelText("Confirmei a fonte oficial"));
    fireEvent.click(
      screen.getByRole("button", { name: "Cadastrar prazo revisado" }),
    );

    await waitFor(() => expect(post).not.toHaveBeenCalled());
  });
});
