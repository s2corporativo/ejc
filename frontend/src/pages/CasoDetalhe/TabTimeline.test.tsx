// @vitest-environment jsdom
// Tela C (Bloco 3) — composer inline de andamentos no topo da timeline:
// registra via POST /cases/{id}/movimentos (tipo + descricao) e recarrega a
// linha do tempo (remontagem do componente de timeline).
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

import api from "../../lib/api";
import TabTimeline from "./TabTimeline";

describe("TabTimeline — composer de andamentos", () => {
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
    // Campo limpo após registrar — pronto para o próximo andamento.
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
});

describe("TabTimeline — lançar horas (achado corrigido)", () => {
  beforeEach(() => {
    vi.spyOn(api, "get").mockResolvedValue({ data: [] });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("envia data + minutos (não `horas`) — schema EntryIn exige os dois", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} });
    render(<TabTimeline caseId="case-1" />);

    fireEvent.click(screen.getByRole("button", { name: /Lançar horas/ }));
    fireEvent.change(screen.getByPlaceholderText(/Elaboração de petição/), {
      target: { value: "Audiência de instrução" },
    });
    fireEvent.change(screen.getByLabelText("Horas"), {
      target: { value: "2.5" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        "/timesheet/",
        expect.objectContaining({
          case_id: "case-1",
          minutos: 150,
          descricao: "Audiência de instrução",
        }),
      );
    });
    const [, payload] = post.mock.calls[0];
    expect(typeof (payload as { data?: unknown }).data).toBe("string");
  });
});

describe("TabTimeline — despesas processuais (F3.2)", () => {
  beforeEach(() => {
    vi.spyOn(api, "get").mockResolvedValue({ data: [] });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("lança despesa via POST /despesas-processuais/", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} });
    render(<TabTimeline caseId="case-1" />);

    fireEvent.click(screen.getByRole("button", { name: /Lançar despesa/ }));
    fireEvent.change(
      screen.getByPlaceholderText(/Cópias autenticadas do processo/),
      { target: { value: "Cópias do processo" } },
    );
    fireEvent.change(screen.getByLabelText("Valor (R$)"), {
      target: { value: "42.50" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        "/despesas-processuais/",
        expect.objectContaining({
          case_id: "case-1",
          valor: 42.5,
          descricao: "Cópias do processo",
          categoria: "outro",
        }),
      );
    });
  });

  it("mostra despesas já lançadas, marcando as faturadas", async () => {
    vi.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/despesas-processuais/casos/case-1") {
        return Promise.resolve({
          data: [
            {
              id: "d1",
              data: "2026-01-10",
              valor: 100,
              descricao: "Custas iniciais",
              faturada: true,
            },
          ],
        });
      }
      return Promise.resolve({ data: [] });
    });
    render(<TabTimeline caseId="case-1" />);

    await waitFor(() => {
      expect(screen.getByText("Custas iniciais")).toBeTruthy();
      expect(screen.getByText("(faturada)")).toBeTruthy();
    });
  });
});
