// @vitest-environment jsdom
// Tela C (Bloco 3) — composer inline de andamentos + contrato do timesheet.
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
import TabTimeline from "./TabTimeline";

describe("TabTimeline — composer de andamentos e timesheet", () => {
  beforeEach(() => {
    vi.spyOn(api, "get").mockResolvedValue({ data: [] });
  });

  afterEach(() => {
    cleanup();
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
    // Barra final = rota canônica; sem ela o backend responde 307 para o
    // prefixo legado (análise E2E 03/09/2026).
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

  it("mantém o formulário aberto e informa erro quando o lançamento falha", async () => {
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
});
