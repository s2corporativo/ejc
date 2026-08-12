// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DptCompany } from "./api";
import DptDiagnosis from "./DptDiagnosis";
import { getDptDiagnosticReadiness, runDptAction } from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    getDptDiagnosticReadiness: vi.fn(),
    runDptAction: vi.fn(),
  };
});

const getReadinessMock = vi.mocked(getDptDiagnosticReadiness);
const runActionMock = vi.mocked(runDptAction);

const EMPRESA: DptCompany = {
  id: "c1",
  nome: "Empresa Teste Ltda",
  status: "ativo",
  casos: 1,
  casos_abertos: 1,
  sinais_criticos: 0,
  providencias_proximas: 0,
};

beforeEach(() => {
  vi.clearAllMocks();
  getReadinessMock.mockResolvedValue({
    client_id: "c1",
    tipo: "completo",
    generated_at: "2026-08-12T00:00:00Z",
    areas: [],
    motivo_persistencia: "",
  } as any);
});

function selecionarArea(): HTMLSelectElement {
  return screen.getByLabelText(/^Área de foco$/i) as HTMLSelectElement;
}

describe("DptDiagnosis → DptIntelligence — sincronização de área", () => {
  it("propaga o tipo de diagnóstico escolhido como área da análise de IA", async () => {
    await act(async () => {
      render(<DptDiagnosis companies={[EMPRESA]} />);
    });
    await waitFor(() => expect(getReadinessMock).toHaveBeenCalled());

    // Padrão: "completo" mapeia para "empresarial" (documentado, não acidental).
    expect(selecionarArea().value).toBe("empresarial");

    const tipoSelect = screen.getByLabelText(/Tipo de diagnóstico/i);
    fireEvent.change(tipoSelect, { target: { value: "tributario" } });

    await waitFor(() => expect(selecionarArea().value).toBe("tributario"));
  });

  it("descarta o rascunho anterior quando o tipo de diagnóstico muda", async () => {
    runActionMock.mockResolvedValue({
      action: "diagnostico",
      client_id: "c1",
      conteudo: "Rascunho tributário",
      fontes: [],
      citacoes: [],
      alertas: [],
      is_rascunho: true,
      requer_revisao: true,
      status_hitl: "gerado",
      aviso_hitl: "Revisão humana obrigatória.",
    });
    await act(async () => {
      render(<DptDiagnosis companies={[EMPRESA]} />);
    });
    await waitFor(() => expect(getReadinessMock).toHaveBeenCalled());

    const textarea = screen.getByPlaceholderText(/Ex\.:/i);
    fireEvent.change(textarea, { target: { value: "Analisar riscos tributários" } });
    const botao = screen.getByRole("button", { name: /gerar rascunho/i });
    await act(async () => {
      botao.click();
    });
    await waitFor(() => expect(screen.getByText("Rascunho tributário")).toBeTruthy());

    const tipoSelect = screen.getByLabelText(/Tipo de diagnóstico/i);
    fireEvent.change(tipoSelect, { target: { value: "ambiental" } });

    await waitFor(() =>
      expect(screen.queryByText("Rascunho tributário")).toBeNull(),
    );
  });
});
