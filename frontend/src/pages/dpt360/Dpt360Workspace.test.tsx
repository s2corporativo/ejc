// @vitest-environment jsdom
import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Dpt360Workspace from "./Dpt360Workspace";
import { getDptCompanyProfile, getDptDashboard } from "./api";

vi.mock("./api", () => ({
  getDptDashboard: vi.fn(),
  getDptCompanyProfile: vi.fn(),
}));

const getDashboardMock = vi.mocked(getDptDashboard);
const getProfileMock = vi.mocked(getDptCompanyProfile);

const DASHBOARD_VAZIO = {
  generated_at: "2026-08-12T00:00:00Z",
  metrics: {
    empresas_acompanhadas: 0,
    riscos_criticos: 0,
    providencias_proximas: 0,
    mudancas_juridicas_hoje: null,
    empresas_potencialmente_impactadas: null,
    diagnosticos_pendentes: null,
  },
  companies: [],
  cases: [],
  deadlines: [],
  priorities: [],
  coverage: "complete" as const,
  notes: [],
};

const PERFIL_FORA_DO_TETO = {
  id: "empresa-fora-do-teto",
  nome: "Empresa Fora do Teto Ltda",
  status: "ativo",
  cidade: "Betim",
  estado: "MG",
  generated_at: "2026-08-12T00:00:00Z",
  health: [],
  twin: [],
  areas_com_casos: [],
  casos_abertos: 0,
  prazos_pendentes: 0,
  documentos: 0,
  sociedades: 0,
  operacoes_lgpd: 0,
  operacoes_lgpd_alto_risco: 0,
  autos_ambientais: 0,
  notes: [],
};

function renderEm(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/dpt360/*" element={<Dpt360Workspace />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  getDashboardMock.mockResolvedValue(DASHBOARD_VAZIO);
});

describe("Dpt360Workspace — Empresa 360 fora do teto do dashboard", () => {
  it("busca o perfil canônico e renderiza a empresa quando ela não está no payload agregado", async () => {
    getProfileMock.mockResolvedValue(PERFIL_FORA_DO_TETO);
    await act(async () => {
      renderEm("/dpt360/empresas/empresa-fora-do-teto");
    });
    await waitFor(() =>
      expect(screen.getByText("Empresa Fora do Teto Ltda")).toBeTruthy(),
    );
    expect(getProfileMock).toHaveBeenCalledWith("empresa-fora-do-teto");
    // Cobertura indisponível deve aparecer — casos/prazos vêm de um payload
    // truncado que não contém esta empresa; "0" não pode virar "nenhum caso".
    expect(screen.getAllByText(/Cobertura indisponível/i).length).toBeGreaterThan(0);
  });

  it("mostra 'não encontrada' apenas quando a API responde 404", async () => {
    getProfileMock.mockRejectedValue({ response: { status: 404 } });
    await act(async () => {
      renderEm("/dpt360/empresas/inexistente");
    });
    await waitFor(() =>
      expect(
        screen.getByText(/Empresa não encontrada na carteira empresarial visível/i),
      ).toBeTruthy(),
    );
  });

  it("distingue falha de rede/servidor de empresa inexistente, e permite tentar novamente", async () => {
    getProfileMock.mockRejectedValueOnce({ response: { status: 500 } });
    await act(async () => {
      renderEm("/dpt360/empresas/empresa-fora-do-teto");
    });
    await waitFor(() =>
      expect(
        screen.getByText(/Não foi possível consultar a empresa agora/i),
      ).toBeTruthy(),
    );
    expect(screen.queryByText(/não encontrada/i)).toBeNull();

    getProfileMock.mockResolvedValueOnce(PERFIL_FORA_DO_TETO);
    const botao = screen.getByRole("button", { name: /tentar novamente/i });
    await act(async () => {
      botao.click();
    });
    await waitFor(() =>
      expect(screen.getByText("Empresa Fora do Teto Ltda")).toBeTruthy(),
    );
  });
});
