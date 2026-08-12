// A2 (auditoria 2026-08-12): durante a análise em voo, selects de Empresa e
// Área e os botões de modo devem estar desabilitados, e o painel do resultado
// deve exibir a empresa e a área analisadas — sem isso, uma troca de empresa
// no meio de uma requisição lenta podia apresentar o rascunho sob a tela errada.
// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DptCompany } from "./api";
import DptIntelligence from "./DptIntelligence";
import { runDptAction } from "./api";

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return {
    ...actual,
    runDptAction: vi.fn(),
  };
});

const runActionMock = vi.mocked(runDptAction);

const RESPOSTA_RASCUNHO = {
  status_hitl: "revisao_obrigatoria",
  alertas: [],
  estruturado: null,
  conteudo: "rascunho de teste",
  fontes: [],
  citacoes: [],
  aviso_hitl: "Revisão humana obrigatória.",
};

const COMPANIES: DptCompany[] = [
  {
    id: "c1",
    nome: "Empresa Alpha",
    status: "ativo",
    casos: 1,
    casos_abertos: 1,
    sinais_criticos: 0,
    providencias_proximas: 0,
  },
  {
    id: "c2",
    nome: "Empresa Beta",
    status: "ativo",
    casos: 0,
    casos_abertos: 0,
    sinais_criticos: 0,
    providencias_proximas: 0,
  },
];

const defaultProps = { companies: COMPANIES, initialClientId: "c1" };

afterEach(() => {
  vi.clearAllMocks();
});

it("selects de empresa e área ficam desabilitados durante o carregamento", async () => {
  let resolve: (v: unknown) => void;
  runActionMock.mockImplementationOnce(
    () => new Promise((res) => { resolve = res; }),
  );

  render(<DptIntelligence {...defaultProps} />);
  fireEvent.change(screen.getByPlaceholderText(/Ex\.:/i), {
    target: { value: "qual o principal risco desta empresa?" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Gerar rascunho/ }));

  const empresaSelect = screen.getByLabelText("Empresa") as HTMLSelectElement;
  const areaSelect = screen.getByLabelText("Área de foco") as HTMLSelectElement;
  expect(empresaSelect.disabled).toBe(true);
  expect(areaSelect.disabled).toBe(true);
  expect(
    (screen.getByRole("button", { name: /Modo Conselho/ }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);

  resolve!(RESPOSTA_RASCUNHO);
  await waitFor(() => expect(empresaSelect.disabled).toBe(false));
  expect(areaSelect.disabled).toBe(false);
});

it("o painel do resultado exibe a empresa e a área analisadas", async () => {
  runActionMock.mockResolvedValueOnce(RESPOSTA_RASCUNHO);
  render(<DptIntelligence {...defaultProps} />);
  fireEvent.change(screen.getByPlaceholderText(/Ex\.:/i), {
    target: { value: "qual o principal risco desta empresa?" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Gerar rascunho/ }));

  await waitFor(() => {
    const painel = screen.getByText(/Empresa Alpha —/).closest("section");
    expect(painel).not.toBeNull();
  });
  expect(screen.getByText("rascunho de teste")).not.toBeNull();
});
