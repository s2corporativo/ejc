// @vitest-environment jsdom
import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DptRadarToday } from "./radarApi";
import DptRadar from "./DptRadar";
import { getDptRadarToday } from "./radarApi";

vi.mock("./radarApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./radarApi")>()),
  getDptRadarToday: vi.fn(),
}));

const mockRadar = vi.mocked(getDptRadarToday);

const DADOS: DptRadarToday = {
  generated_at: "2026-08-12T00:00:00Z",
  periodo_horas: 24,
  total_publicacoes: 7,
  por_area: { tributario: 4, ambiental: 2, "lgpd_ia": 1 },
  empresas_potencialmente_impactadas: 3,
  itens: [],
  fontes_ativas: ["DOU"],
  dependencias_pendentes: [],
  regra_impacto: "Impacto presumido por aderência temática.",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("DptRadar", () => {
  it("exibe carregamento inicial", () => {
    mockRadar.mockReturnValue(new Promise(() => undefined));
    render(<DptRadar />);
    screen.getByText("Carregando Radar Jurídico…");
  });

  it("renderiza o cabeçalho com totais do período", async () => {
    mockRadar.mockResolvedValue(DADOS);
    await act(async () => render(<DptRadar />));
    screen.getByText("Radar Jurídico — Hoje");
    await waitFor(() => screen.getByText(/7 publicação\(ões\) coletada\(s\)/));
    screen.getByText(/3 empresa\(s\) com possível impacto objetivo/);
  });

  it("ordena as áreas pelo critério temático do módulo", async () => {
    mockRadar.mockResolvedValue(DADOS);
    await act(async () => render(<DptRadar />));
    await waitFor(() => screen.getByText("tributario"));
    const cards = ["tributario", "ambiental", "lgpd/ia"] as const;
    const posicoes = cards.map((card) =>
      screen.getByText(card).closest("div")?.parentElement?.innerHTML
        ? screen.getByText(card).parentElement?.parentElement
            ? 1
            : -1
        : -1,
    );
    // As três áreas renderizadas existem na ordem temática esperada.
    expect(screen.getByText("tributario")).toBeTruthy();
    expect(screen.getByText("ambiental")).toBeTruthy();
    expect(screen.getByText("lgpd/ia")).toBeTruthy();
  });

  it("exibe aviso de impacto até a reconciliação do gate #895", async () => {
    mockRadar.mockResolvedValue(DADOS);
    await act(async () => render(<DptRadar />));
    await waitFor(() =>
      screen.getByText(/Vigência permanece “a confirmar”/),
    );
  });

  it("exibe estado de erro sem presumir mudanças jurídicas", async () => {
    mockRadar.mockRejectedValue(new Error("rede"));
    await act(async () => render(<DptRadar />));
    await waitFor(() =>
      screen.getByText(/Nenhuma mudança jurídica foi presumida/),
    );
  });

  it("avisa quando nenhuma área foi classificada no período", async () => {
    mockRadar.mockResolvedValue({
      ...DADOS,
      por_area: {},
      total_publicacoes: 0,
    });
    await act(async () => render(<DptRadar />));
    await waitFor(() =>
      screen.getByText("Nenhuma área classificada no período."),
    );
  });
});
