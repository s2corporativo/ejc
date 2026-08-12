// @vitest-environment jsdom
import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DptCompanyProfile } from "./api";
import CompanyLegalTwin from "./CompanyLegalTwin";
import { getDptCompanyProfile } from "./api";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  getDptCompanyProfile: vi.fn(),
}));

const mockProfile = vi.mocked(getDptCompanyProfile);

const PERFIL: DptCompanyProfile = {
  id: "c1",
  nome: "Empresa Jurídico Vivo Ltda",
  status: "ativo",
  cidade: "Belo Horizonte",
  estado: "MG",
  generated_at: "2026-08-12T00:00:00Z",
  health: [
    {
      area: "Tributário",
      classificacao: "Regular",
      justificativa: "Sem pendências fiscais no período.",
      evidencias: 2,
    },
  ],
  twin: [
    {
      key: "societario",
      label: "Societário",
      status: "com_dados",
      registros: 3,
      canonical_path: "/societaria/contrato-social",
    },
    {
      key: "lgpd",
      label: "LGPD",
      status: "sem_dados",
      registros: 0,
    },
    {
      key: "ambiental",
      label: "Ambiental",
      status: "nao_aplicavel",
      registros: 0,
    },
  ],
  areas_com_casos: ["tributario"],
  casos_abertos: 1,
  prazos_pendentes: 2,
  documentos: 10,
  sociedades: 3,
  operacoes_lgpd: 0,
  operacoes_lgpd_alto_risco: 0,
  autos_ambientais: 0,
  notes: [],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("CompanyLegalTwin", () => {
  it("exibe o cabeçalho DPT Legal Twin", async () => {
    mockProfile.mockResolvedValue(PERFIL);
    await act(async () =>
      render(
        <MemoryRouter>
          <CompanyLegalTwin clientId="c1" />
        </MemoryRouter>,
      ),
    );
    screen.getByText("DPT Legal Twin");
    screen.getByText("Projeção rastreável");
  });

  it("não transforma ausência de registro em regularidade", async () => {
    mockProfile.mockResolvedValue(PERFIL);
    await act(async () =>
      render(
        <MemoryRouter>
          <CompanyLegalTwin clientId="c1" />
        </MemoryRouter>,
      ),
    );
    screen.getByText(
      /não transforma ausência de registro em regularidade jurídica/i,
    );
  });

  it("renderiza as dimensões do twin com status corretos", async () => {
    mockProfile.mockResolvedValue(PERFIL);
    await act(async () =>
      render(
        <MemoryRouter>
          <CompanyLegalTwin clientId="c1" />
        </MemoryRouter>,
      ),
    );
    await waitFor(() => screen.getByText("Societário"));
    screen.getByText("Com dados");
    screen.getByText("Sem dados");
    screen.getByText("N/A");
  });

  it("linka a fonte canônica quando presente", async () => {
    mockProfile.mockResolvedValue(PERFIL);
    await act(async () =>
      render(
        <MemoryRouter>
          <CompanyLegalTwin clientId="c1" />
        </MemoryRouter>,
      ),
    );
    await waitFor(() => screen.getByText("Societário"));
    const link = screen.getByRole("link", { name: /Abrir fonte/i });
    expect(link.getAttribute("href")).toBe("/societaria/contrato-social");
  });

  it("renderiza a saúde jurídica por área", async () => {
    mockProfile.mockResolvedValue(PERFIL);
    await act(async () =>
      render(
        <MemoryRouter>
          <CompanyLegalTwin clientId="c1" />
        </MemoryRouter>,
      ),
    );
    await waitFor(() => screen.getByText("Saúde jurídica por área"));
    screen.getByText("Tributário");
    screen.getByText("Regular");
    screen.getByText(/Sem pendências fiscais no período/);
  });

  it("exibe erro quando a API falha", async () => {
    mockProfile.mockRejectedValue(new Error("rede"));
    await act(async () =>
      render(
        <MemoryRouter>
          <CompanyLegalTwin clientId="c1" />
        </MemoryRouter>,
      ),
    );
    await waitFor(() =>
      screen.getByText(
        /Não foi possível carregar o Perfil Jurídico Vivo desta empresa/,
      ),
    );
  });
});
