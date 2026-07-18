import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("../../lib/api", () => ({
  default: { get },
}));

vi.mock("../../components/CaseBreadcrumb", () => ({
  default: () => <div>TRILHA_DO_CASO</div>,
}));

vi.mock("../../components/Toast", () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));

import JornadaCaso from "../JornadaCaso";

const ORQUESTRADOR = {
  case_id: "case-1",
  estado: "estrategia",
  estado_rotulo: "Estratégia (matriz de teses)",
  estados: ["entrada", "compreensao", "classificacao", "estrategia"],
  proximo_passo: {
    estado: "estrategia",
    estado_rotulo: "Estratégia (matriz de teses)",
    passo_recomendado: "Definir a estratégia e encaminhar a contratação.",
    acoes_disponiveis: [],
    pendencias_bloqueantes: [
      {
        tipo: "aprovacao_humana",
        detalhe: "Nenhuma tese aprovada pelo advogado.",
      },
    ],
  },
  jornada: [
    { etapa: "documentos_lidos", rotulo: "Documentos lidos", status: "concluida" },
    { etapa: "estrategia_aprovada", rotulo: "Estratégia aprovada", status: "bloqueada" },
    { etapa: "peca_redigida", rotulo: "Peça redigida", status: "pendente" },
  ],
  linha_do_tempo: [],
};

describe("JornadaCaso — fonte única no Orquestrador", () => {
  beforeEach(() => {
    get.mockReset();
    get.mockImplementation((url: string) => {
      if (url === "/cases/case-1/orquestrador") {
        return Promise.resolve({ data: ORQUESTRADOR });
      }
      if (url === "/cases/case-1") {
        return Promise.resolve({
          data: {
            id: "case-1",
            titulo: "Ação de teste",
            numero_processo: "0000000-00.2026.8.13.0000",
          },
        });
      }
      return Promise.reject(new Error(`URL inesperada: ${url}`));
    });
  });

  it("não consulta a jornada legada e mostra o próximo passo determinístico", async () => {
    render(
      <MemoryRouter initialEntries={["/casos/case-1/jornada"]}>
        <Routes>
          <Route path="/casos/:id/jornada" element={<JornadaCaso />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Definir a estratégia e encaminhar a contratação."),
    ).toBeTruthy();
    expect(screen.getByText("Estratégia (matriz de teses)")).toBeTruthy();
    expect(screen.getByText("Nenhuma tese aprovada pelo advogado.")).toBeTruthy();

    await waitFor(() => {
      expect(get).toHaveBeenCalledWith("/cases/case-1/orquestrador");
      expect(get).toHaveBeenCalledWith("/cases/case-1");
    });

    expect(
      get.mock.calls.some(([url]) => String(url).includes("/casos/case-1/jornada")),
    ).toBe(false);
  });
});
