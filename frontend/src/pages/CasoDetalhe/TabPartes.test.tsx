import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TabPartes from "./TabPartes";

const getMock = vi.fn();
const postMock = vi.fn();
const toastError = vi.fn();

vi.mock("../../lib/api", () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    delete: vi.fn(),
  },
}));
vi.mock("../../components/Toast", () => ({
  toast: { error: (m: unknown) => toastError(m), success: vi.fn() },
}));

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
  toastError.mockReset();
});

function erroHttp(status: number, detail?: unknown) {
  return Object.assign(new Error(`HTTP ${status}`), {
    response: { status, data: { detail } },
  });
}

describe("TabPartes (S7)", () => {
  it("falha de carga vira ErrorState e o retry recarrega", async () => {
    getMock.mockRejectedValueOnce(erroHttp(503));
    render(<TabPartes caseId="c1" />);
    expect((await screen.findByRole("alert")).textContent).toMatch(
      /Não foi possível carregar as partes/,
    );
    getMock.mockResolvedValueOnce({
      data: [{ id: "p1", nome: "Maria", tipo: "autor" }],
    });
    fireEvent.click(screen.getByRole("button", { name: /Tentar novamente/ }));
    await waitFor(() => expect(screen.getByText("Maria")).toBeTruthy());
  });

  it("salvar com erro 422 mostra toast leigo em vez de silêncio (D6)", async () => {
    getMock.mockResolvedValue({ data: [] });
    postMock.mockRejectedValueOnce(
      erroHttp(422, [{ loc: ["body", "nome"], msg: "campo obrigatório" }]),
    );
    render(<TabPartes caseId="c1" />);
    await screen.findByText(/Partes Processuais/);
    fireEvent.click(screen.getByRole("button", { name: /Adicionar/ }));
    fireEvent.submit(document.querySelector("form") as HTMLFormElement);
    await waitFor(() => expect(toastError).toHaveBeenCalledTimes(1));
    const msg = String(toastError.mock.calls[0][0]);
    expect(msg).toMatch(/nome/);
    expect(msg).not.toMatch(/\[object/);
  });
});
