// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import api from "../../lib/api";
import TabDocumentos from "./TabDocumentos";

vi.mock("../../stores/auth", () => ({
  useAuth: (selector: (state: unknown) => unknown) =>
    selector({ user: { id: "user-1", role: "advogado" } }),
}));

const DOC = {
  id: "doc-1",
  titulo: "Contrato social",
  filename: "contrato.pdf",
  tipo: "contrato",
};

describe("TabDocumentos — ações contextuais do caso", () => {
  beforeEach(() => {
    vi.spyOn(api, "get").mockImplementation((url: string) => {
      if (url === "/documents/?case_id=case-1") {
        return Promise.resolve({ data: { data: [DOC] } });
      }
      if (url === "/casos/case-1/solicitacoes-documentos") {
        return Promise.resolve({ data: { data: [] } });
      }
      if (url === "/cases/case-1") {
        return Promise.resolve({ data: { id: "case-1", client_id: "client-1" } });
      }
      return Promise.resolve({ data: [] });
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("solicita documento pelo fluxo canônico do Caso", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { id: "s1" } });
    render(<TabDocumentos caseId="case-1" />);

    fireEvent.click(
      await screen.findByRole("button", { name: /Solicitar ao cliente/ }),
    );
    fireEvent.change(
      screen.getByPlaceholderText(/comprovante de residência atualizado/i),
      { target: { value: "Comprovante de residência" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /Enviar solicitação/ }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        "/casos/case-1/solicitacoes-documentos",
        {
          itens: [
            {
              nome: "Comprovante de residência",
              descricao: undefined,
            },
          ],
          mensagem: undefined,
        },
      );
    });
  });

  it("solicita assinatura sem pedir novamente cliente e documento", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { id: "sig-1" } });
    render(<TabDocumentos caseId="case-1" />);

    const botao = await screen.findByRole("button", {
      name: /Solicitar assinatura/,
    });
    await waitFor(() => expect((botao as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(botao);

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith("/signatures/", {
        document_id: "doc-1",
        client_id: "client-1",
      });
    });
  });
});
