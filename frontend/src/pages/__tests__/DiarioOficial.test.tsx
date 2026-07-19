/**
 * Regressão do erro de console/crash em /diario-oficial (item 2.2): `.map` sobre
 * resposta não-array. O endpoint /diario-oficial/alertas devolve {items:[...]}.
 * Renderiza a página com a API mockada nessa forma (e num objeto de erro) e falha
 * se voltar a quebrar.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// vi.hoisted: o factory de vi.mock é içado ao topo — precisa acessar `get` assim.
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("../../lib/api", () => ({
  default: {
    get,
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));
vi.mock("../../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import DiarioOficial from "../DiarioOficial";

const renderPage = () =>
  render(
    <MemoryRouter>
      <DiarioOficial />
    </MemoryRouter>,
  );

describe("DiarioOficial — resposta não-array não quebra o render", () => {
  beforeEach(() => get.mockReset());

  it("alertas como envelope {items:[]} → renderiza sem lançar", async () => {
    // Envelope em alertas (via .items) + contador via {nao_lidos} + keywords [].
    get.mockImplementation((url = "") => {
      if (url.includes("/keywords")) return Promise.resolve({ data: [] });
      return Promise.resolve({ data: { total: 0, items: [], nao_lidos: 0 } });
    });
    renderPage();
    // Âncora estável: espera o heading do PageHeader aparecer (findBy* faz retry
    // até o re-render pós-loading) em vez de checar document.body.textContent logo
    // após a chamada da API — essa checagem pegava o Spinner (sem texto) e falhava
    // de forma intermitente ("expected 0 to be greater than 0").
    expect(
      await screen.findByRole("heading", { name: /Diário Oficial/ }),
    ).toBeTruthy();
  });

  it("API devolvendo objeto de erro (não-array) → ainda não quebra", async () => {
    get.mockResolvedValue({ data: { detail: "erro qualquer" } });
    renderPage();
    expect(
      await screen.findByRole("heading", { name: /Diário Oficial/ }),
    ).toBeTruthy();
  });
});
