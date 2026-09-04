// @vitest-environment jsdom
// Tela C — composer inline de andamentos, timesheet e despesas processuais.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

vi.mock("../../components/visual/LinhaDoTempoProcessual", () => ({
  default: ({ caseId }: { caseId: string }) => (
    <div>TIMELINE_VISUAL:{caseId}</div>
  ),
}));

vi.mock("../../components/Toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

import { toast } from "../../components/Toast";
import api from "../../lib/api";
import { useAuth } from "../../stores/auth";
import TabTimeline from "./TabTimeline";

describe("TabTimeline — andamentos, timesheet e despesas processuais", () => {
  beforeEach(() => {
    useAuth.setState({ user: null, status: "unauthenticated" });
    vi.spyOn(api, "get").mockResolvedValue({ data: [] });
  });

  afterEach(() => {
    cleanup();
    useAuth.setState({ user: null, status: "unauthenticated" });
    vi.restoreAllMocks();
  });

  it("não registra andamento vazio", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} });
    render(<TabTimeline caseId="case-1" />);

    const botao = screen.getByRole("button", {
      name: /Registrar andamento/,
    }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
    expect(post).not.toHaveBeenCalled();
  });

  it("envia tipo + descricao para POST /cases/{id}/movimentos", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} });
    render(<TabTimeline caseId="case-1" />);

    fireEvent.change(screen.getByLabelText("Tipo do andamento"), {
      target: { value: "decisao" },
    });
    fireEvent.change(
      screen.getByPlaceholderText(/O que aconteceu neste caso/),
      { target: { value: "Sentença publicada no DJe." } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: /Registrar andamento/ }),
    );

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith("/cases/case-1/movimentos", {
        tipo: "decisao",
        descricao: "Sentença publicada no DJe.",
      });
    });
    await waitFor(() => {
      expect(
        (
          screen.getByPlaceholderText(
            /O que aconteceu neste caso/,
          ) as HTMLTextAreaElement
        ).value,
      ).toBe("");
    });
  });

  it("converte horas para minutos e envia o contrato canônico do timesheet", async () => {
    const post = vi
      .spyOn(api, "post")
      .mockResolvedValue({ data: { id: "ts-1" } });
    render(<TabTimeline caseId="case-1" />);

    fireEvent.click(screen.getByRole("button", { name: /Lançar horas/ }));
    fireEvent.change(
      screen.getByPlaceholderText("Ex: Elaboração de petição..."),
      { target: { value: "Revisão de contrato" } },
    );
    fireEvent.change(screen.getByRole("spinbutton"), {
      target: { value: "1.5" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [url, payload] = post.mock.calls[0];
    expect(url).toBe("/timesheet/");
    expect(payload).toMatchObject({
      case_id: "case-1",
      minutos: 90,
      descricao: "Revisão de contrato",
      faturavel: true,
    });
    expect((payload as Record<string, unknown>).horas).toBeUndefined();
    expect((payload as Record<string, unknown>).data).toMatch(
      /^\d{4}-\d{2}-\d{2}$/,
    );
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/timesheet/casos/case-1"),
    );
    expect(vi.mocked(toast.success)).toHaveBeenCalledWith(
      "Horas lançadas no caso.",
    );
  });

  it("mantém o formulário de horas aberto quando o lançamento falha", async () => {
    vi.spyOn(api, "post").mockRejectedValue({
      response: { data: { detail: "Falha fictícia de validação" } },
    });
    render(<TabTimeline caseId="case-1" />);

    fireEvent.click(screen.getByRole("button", { name: /Lançar horas/ }));
    const atividade = screen.getByPlaceholderText(
      "Ex: Elaboração de petição...",
    ) as HTMLInputElement;
    fireEvent.change(atividade, { target: { value: "Atividade fictícia" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() =>
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith(
        "Falha fictícia de validação",
      ),
    );
    expect(screen.getByRole("button", { name: "Salvar" })).toBeTruthy();
    expect(atividade.value).toBe("Atividade fictícia");
  });

  it("lança despesa processual sem sair do caso", async () => {
    const post = vi
      .spyOn(api, "post")
      .mockResolvedValue({ data: { id: "desp-1" } });
    render(<TabTimeline caseId="case-1" />);

    fireEvent.click(screen.getByRole("button", { name: /Lançar despesa/ }));
    fireEvent.change(
      screen.getByPlaceholderText(/custas de distribuição, diligência/),
      { target: { value: "Custas de distribuição" } },
    );
    fireEvent.change(screen.getByPlaceholderText("0,00"), {
      target: { value: "125,50" },
    });
    const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
    fireEvent.change(selects[selects.length - 1], {
      target: { value: "custas" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Salvar despesa" }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        "/despesas-processuais/",
        expect.objectContaining({
          case_id: "case-1",
          valor: 125.5,
          descricao: "Custas de distribuição",
          categoria: "custas",
        }),
      );
    });
    expect(vi.mocked(toast.success)).toHaveBeenCalledWith(
      "Despesa processual lançada.",
    );
  });

  it("advogado pode gerar reembolso das despesas pendentes", async () => {
    useAuth.setState({
      user: { id: "adv-1", role: "advogado", email: "adv@teste.local" } as any,
      status: "authenticated",
    });
    vi.mocked(api.get).mockImplementation(async (url) => {
      if (String(url).includes("/despesas-processuais/casos/")) {
        return {
          data: {
            data: [
              {
                id: "desp-1",
                data: "2026-09-01",
                valor: 100,
                descricao: "Diligência",
                categoria: "diligencia",
                faturada: false,
              },
            ],
            total: 100,
            pendente_de_faturar: 100,
          },
        } as any;
      }
      return { data: [] } as any;
    });
    const post = vi.spyOn(api, "post").mockResolvedValue({
      data: { fee_id: "fee-1", valor: 100, lancamentos: 1 },
    });

    render(<TabTimeline caseId="case-1" />);
    const botao = await screen.findByRole("button", {
      name: "Gerar reembolso",
    });
    fireEvent.click(botao);

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        "/despesas-processuais/caso/case-1/faturar",
        {},
      ),
    );
    expect(vi.mocked(toast.success)).toHaveBeenCalledWith(
      expect.stringContaining("Reembolso gerado"),
    );
  });
});
