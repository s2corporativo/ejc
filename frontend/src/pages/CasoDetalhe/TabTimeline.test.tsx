// @vitest-environment jsdom
// Tela C (Bloco 3) — composer inline de andamentos no topo da timeline:
// registra via POST /cases/{id}/movimentos (tipo + descricao) e recarrega a
// linha do tempo (remontagem do componente de timeline).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

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
    fireEvent.click(screen.getByRole("button", { name: /Registrar andamento/ }));

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
