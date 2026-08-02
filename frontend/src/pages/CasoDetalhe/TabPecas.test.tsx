// @vitest-environment jsdom
// Tela C (Bloco 3) — aba Peças do caso:
//   • lista as peças do caso (GET /legal-docs/?case_id=...);
//   • peça em minuta oferece "Baixar PDF da minuta" e "Conferir e assinar";
//   • peça assinada oferece apenas "Baixar PDF";
//   • HITL inegociável: a assinatura exige observações não vazias e só chama
//     POST /legal-docs/{id}/conferir-e-assinar após confirmação no modal.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import api from "../../lib/api";
import TabPecas from "./TabPecas";

const PECAS = [
  {
    id: "p1",
    titulo: "Petição inicial — cobrança",
    tipo_peca: "peticao_inicial",
    status: "rascunho",
    versao: 1,
    ai_generated: true,
    human_reviewed: false,
    case_id: "case-1",
  },
  {
    id: "p2",
    titulo: "Contestação assinada",
    tipo_peca: "contestacao",
    status: "aprovada",
    versao: 2,
    ai_generated: false,
    human_reviewed: true,
    case_id: "case-1",
  },
];

function renderTab() {
  return render(
    <MemoryRouter>
      <TabPecas caseId="case-1" />
    </MemoryRouter>,
  );
}

describe("TabPecas — o caso como espaço de trabalho", () => {
  beforeEach(() => {
    vi.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/legal-docs/") {
        return Promise.resolve({ data: { data: PECAS, total: 2 } });
      }
      return Promise.resolve({ data: [] });
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("lista as peças do caso com as ações certas por status", async () => {
    renderTab();

    expect(await screen.findByText("Petição inicial — cobrança")).toBeTruthy();
    expect(screen.getByText("Contestação assinada")).toBeTruthy();

    // Minuta: PDF de leitura + ato de conferência; assinada: PDF de protocolo.
    expect(
      screen.getByRole("button", { name: /Baixar PDF da minuta/ }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /Conferir e assinar/ }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: /^Baixar PDF$/ })).toBeTruthy();

    // Deep-link para o módulo de redação preserva o caso selecionado.
    const link = screen.getByRole("link", { name: /Abrir no módulo Peças/ });
    expect(link.getAttribute("href")).toBe("/pecas?caso=case-1");
  });

  it("HITL: não assina sem observações e envia o payload exato ao confirmar", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} });
    renderTab();

    fireEvent.click(
      await screen.findByRole("button", { name: /Conferir e assinar/ }),
    );

    // Modal aberto: o botão de assinatura nasce DESABILITADO (observações
    // obrigatórias — mesma exigência do módulo Peças).
    const botoes = screen.getAllByRole("button", {
      name: /Conferir e assinar/,
    });
    const confirmar = botoes[botoes.length - 1] as HTMLButtonElement;
    expect(confirmar.disabled).toBe(true);
    expect(post).not.toHaveBeenCalled();

    fireEvent.change(
      screen.getByPlaceholderText("Observações da revisão (obrigatório)"),
      { target: { value: "Conferi fatos, pedidos e jurisprudência." } },
    );
    expect(confirmar.disabled).toBe(false);

    fireEvent.click(confirmar);
    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        "/legal-docs/p1/conferir-e-assinar",
        { observacoes: "Conferi fatos, pedidos e jurisprudência." },
      );
    });
  });

  it("cancelar o modal não dispara nenhuma chamada", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} });
    renderTab();

    fireEvent.click(
      await screen.findByRole("button", { name: /Conferir e assinar/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: /^Cancelar$/ }));
    expect(post).not.toHaveBeenCalled();
  });
});
