// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import api from "../lib/api";
import Checklists from "./Checklists";

vi.mock("../lib/api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const getMock = vi.mocked(api.get);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Checklists — erro explícito", () => {
  it("não apresenta falha da API como lista vazia nem oferece criação sem carga válida", async () => {
    getMock.mockRejectedValueOnce(new Error("falha fictícia"));

    render(<Checklists />);

    await waitFor(() =>
      expect(
        screen.getByText("Não foi possível carregar os checklists."),
      ).toBeTruthy(),
    );
    expect(screen.queryByText(/nenhum template ainda/i)).toBeNull();

    const botao = screen.getByRole("button", { name: /novo template/i });
    expect((botao as HTMLButtonElement).disabled).toBe(true);
  });
});
