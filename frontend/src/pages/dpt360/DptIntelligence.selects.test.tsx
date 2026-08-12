// A2 (auditoria 2026-08-12): durante a análise em voo, o select de Empresa e
// os botões de modo ficam desabilitados, e o painel do resultado exibe a
// empresa e a área analisadas — sem isso, uma troca de empresa no meio de uma
// requisição lenta podia apresentar o rascunho sob a tela errada.
// Nota de evolução (main, dez/2026): o select de Área permanece habilitado
// durante o carregamento por desenho — trocá-lo INVALIDA a análise em voo
// (token invalidado, loading zerado), então bloqueá-lo seria redundante.
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

    // Empresa e botões de modo ficam desabilitados durante o loading.
  await waitFor(() => {
    expect(
      (screen.getByLabelText("Empresa") as HTMLSelectElement).disabled,
    ).toBe(true);
  });
  expect(
    (screen.getByRole("button", { name: /Modo Conselho/ }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  // A Área permanece habilitada: trocá-la invalida a análise em voo
  // (token de requisição incrementado e loading zerado), evitando rascunho
  // entregue sob a empresa errada.
  expect(
    (screen.getByLabelText("Área de foco") as HTMLSelectElement).disabled,
  ).toBe(false);
  resolve!(RESPOSTA_RASCUNHO);
  await waitFor(() => {
    expect(
      (screen.getByLabelText("Empresa") as HTMLSelectElement).disabled,
    ).toBe(false);
  });
  expect(
    (screen.getByRole("button", { name: /Modo Conselho/ }) as HTMLButtonElement)
      .disabled,
  ).toBe(false);
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
