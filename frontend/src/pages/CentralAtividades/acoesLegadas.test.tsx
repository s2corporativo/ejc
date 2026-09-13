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
      dias_uteis: false,
      tribunal: null,
      dobro: false,
      excecao_recesso_penal: false,
    });
    expect(post).not.toHaveBeenCalledWith(
      "/suspensoes/simular",
      expect.anything(),
    );
  });

  it("exibe regra auditável e revisão humana obrigatória após simular", async () => {
    const { container } = render(
      <SimularPrazoModal open={true} onClose={vi.fn()} />,
    );

    const data = container.querySelector('input[type="date"]') as HTMLInputElement;
    fireEvent.change(data, { target: { value: "2026-09-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Simular" }));

    await waitFor(() =>
      expect(
        screen.getByText(/Referência normativa: CPC, arts\. 219 e 220/),
      ).toBeTruthy(),
    );
    expect(screen.getByText(/Abrir texto oficial no Planalto/)).toBeTruthy();
    expect(screen.getByText(/Revisão humana obrigatória/)).toBeTruthy();
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

  it("só cria prazo após o advogado informar o vencimento conferido", async () => {
    const onClose = vi.fn();
    const onResolvido = vi.fn();
    const { container } = render(
      <PrazoSugeridoModal
        sugestao={{
          id: "com-1",
          titulo: "Intimação de teste",
          dados: {
            disponivel: true,
            data_sugerida: "2026-09-18",
            dias: 15,
            prazo_sugerido_status: "nenhum",
          },
        }}
        onClose={onClose}
        onResolvido={onResolvido}
      />,
    );

    // A referência automática aparece, mas não materializa prazo.
    expect(screen.getByText(/Referência automática/)).toBeTruthy();

    const aceitar = screen.getByRole("button", {
      name: "Aceitar e criar prazo",
    }) as HTMLButtonElement;
    expect(aceitar.disabled).toBe(true);

    const vencimento = container.querySelector(
      'input[type="date"]',
    ) as HTMLInputElement;
    expect(vencimento).toBeTruthy();
    fireEvent.change(vencimento, { target: { value: "2026-09-22" } });
    expect(aceitar.disabled).toBe(false);

    fireEvent.click(aceitar);
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/intimacoes/com-1/aceitar-prazo", {
        data_prazo: "2026-09-22",
      }),
    );
    await waitFor(() => expect(onResolvido).toHaveBeenCalledTimes(1));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("não envia nada enquanto o vencimento conferido não é informado", async () => {
    render(
      <PrazoSugeridoModal
        sugestao={{
          id: "com-sem-data",
          titulo: "Intimação sem data",
          dados: {
            disponivel: false,
            prazo_sugerido_status: "nenhum",
          },
        }}
        onClose={vi.fn()}
        onResolvido={vi.fn()}
      />,
    );

    // Sem base calculável, o motivo aparece — mas o caminho é HITL: nada é
    // enviado automaticamente.
    expect(
      screen.getByText(/A captura não fornece base suficiente/i),
    ).toBeTruthy();
    const aceitar = screen.getByRole("button", {
      name: "Aceitar e criar prazo",
    }) as HTMLButtonElement;
    expect(aceitar.disabled).toBe(true);
    expect(post).not.toHaveBeenCalled();
  });

  it("recusar prazo não envia data e não cria Deadline", async () => {
    render(
      <PrazoSugeridoModal
        sugestao={{
          id: "com-recusa",
          titulo: "Intimação recusável",
          dados: {
            disponivel: true,
            data_sugerida: "2026-09-18",
            prazo_sugerido_status: "nenhum",
          },
        }}
        onClose={vi.fn()}
        onResolvido={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Recusar prazo" }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith("/intimacoes/com-recusa/recusar-prazo"),
    );
    expect(post).not.toHaveBeenCalledWith(
      "/intimacoes/com-recusa/aceitar-prazo",
      expect.anything(),
    );
  });
});
