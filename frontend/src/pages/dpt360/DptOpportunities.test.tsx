// @vitest-environment jsdom
import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DptOpportunityQueueItem } from "./api";
import DptOpportunities from "./DptOpportunities";
import { getDptOpportunityQueue } from "./api";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  getDptOpportunityQueue: vi.fn(),
}));

const filaMock = vi.mocked(getDptOpportunityQueue);

const ITEM: DptOpportunityQueueItem = {
  intake_id: "abc123def4567890",
  status: "triagem",
  created_at: "2026-08-11T12:00:00Z",
  origem: "Entrada Universal",
  urgencia_declarada: "alta",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("DptOpportunities", () => {
  it("exibe estado de carregamento inicial", () => {
    filaMock.mockReturnValue(new Promise(() => undefined));
    render(<DptOpportunities />);
    // O Spinner é visual (sem texto próprio); o estado de carregamento é o
    // contêiner centralizado apresentado enquanto a fila não resolve. A
    // asserção verifica a ausência do título do estado resolvido.
    // O título só aparece depois que a fila resolve; o contêiner de
    // carregamento (grid centralizado) está presente enquanto carrega.
    expect(screen.queryByText("Oportunidades em triagem")).toBeNull();
  });

  it("carrega e exibe a fila de oportunidades", async () => {
    filaMock.mockResolvedValue([ITEM]);
    await act(async () => render(<DptOpportunities />));
    screen.getByText("Oportunidades em triagem");
    await waitFor(() => screen.getByText(/Intake abc123de…/));
    screen.getByText(/Origem não informada|Entrada Universal/);
  });

  it("exibe estado vazio quando a fila está vazia", async () => {
    filaMock.mockResolvedValue([]);
    await act(async () => render(<DptOpportunities />));
    await waitFor(() =>
      screen.getByText(
        /Nenhuma oportunidade pendente está visível no seu escopo/,
      ),
    );
  });

  it("exibe erro quando a API falha", async () => {
    filaMock.mockRejectedValue(new Error("rede"));
    await act(async () => render(<DptOpportunities />));
    await waitFor(() =>
      screen.getByText(
        /Não foi possível carregar a fila de oportunidades empresariais/,
      ),
    );
  });
});
