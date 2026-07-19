/**
 * Regressão do bug de TELA BRANCA em /sociedade (item 2.1).
 *
 * A causa foi um `.reduce`/`.map` sobre uma resposta que NÃO era array (o
 * endpoint /sociedade/distribuicao devolve um envelope {items:[...]}). Estes
 * testes renderizam a página com a API mockada devolvendo justamente formas
 * NÃO-array e falham se o componente voltar a quebrar no render.
 *
 * É exatamente a classe de teste que teria pego o bug antes de produção.
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

import Sociedade from "../Sociedade";

const renderPage = () =>
  render(
    <MemoryRouter>
      <Sociedade />
    </MemoryRouter>,
  );

describe("Sociedade — resposta não-array não quebra o render", () => {
  beforeEach(() => get.mockReset());

  it("distribuicao como envelope {items:[]} → renderiza sem lançar", async () => {
    // Todas as chamadas devolvem um ENVELOPE (não um array cru): distribuicao
    // via .items, socios via .socios — exatamente a forma que causava o crash.
    get.mockResolvedValue({
      data: {
        items: [],
        socios: [],
        total_participacao: 0,
        total: 0,
        data: [],
      },
    });
    renderPage();
    // Não houve tela branca: aguarda o conteúdo REAL da página (o card
    // "Sócios ativos", renderizado só depois de sair do estado de loading —
    // o título agora vive no FinanceiroWorkspace, não mais nesta página).
    // Ancorar em conteúdo pós-loading evita a race em que a asserção rodava
    // enquanto o Spinner (sem texto) ainda estava na tela.
    expect(await screen.findByText(/Sócios ativos/)).toBeTruthy();
  });

  it("API devolvendo objeto de erro (não-array) → ainda não quebra", async () => {
    get.mockResolvedValue({ data: { detail: "erro qualquer" } });
    renderPage();
    expect(await screen.findByText(/Sócios ativos/)).toBeTruthy();
  });
});
