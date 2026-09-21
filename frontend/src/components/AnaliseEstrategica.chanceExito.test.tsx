// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const postMock = vi.fn();

vi.mock("../lib/api", () => ({
  default: { post: (...args: unknown[]) => postMock(...args) },
}));

vi.mock("../lib/iaStatus", () => ({
  useIaStatus: () => ({ disponivel: true, mensagem: null }),
}));

vi.mock("../lib/iaErro", () => ({
  ROTULO_IA_NAO_ATIVADA: "IA não ativada",
  mensagemErroIA: () => "erro",
}));

import AnaliseEstrategica from "./AnaliseEstrategica";

afterEach(() => {
  cleanup();
  postMock.mockReset();
});

it("não exibe percentual de êxito produzido pela IA", async () => {
  postMock.mockResolvedValue({
    data: {
      jurimetria: {
        chance_sucesso_percent: 87,
        tempo_estimado_meses: 12,
        base_estimativa: "texto do modelo",
      },
      alertas: [],
    },
  });

  render(<AnaliseEstrategica caseId="case-ficticio" />);
  fireEvent.click(
    screen.getByRole("button", { name: /Executar Análise Estratégica/i }),
  );

  await waitFor(() => expect(postMock).toHaveBeenCalled());
  expect(await screen.findByText("Não estimada por IA")).toBeTruthy();
  expect(screen.getByText(/Probabilidade de êxito/i)).toBeTruthy();
  expect(screen.queryByText("87%")).toBeNull();
  expect(screen.queryByText("Chance de Êxito")).toBeNull();
});
