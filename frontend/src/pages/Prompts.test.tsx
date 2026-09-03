import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Prompts, { PAPEIS_EXCLUIR_PROMPT } from "./Prompts";

const getMock = vi.fn();
let role = "estagiario";

vi.mock("../lib/api", () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));
vi.mock("../stores/auth", () => ({
  useAuth: (selector: (s: { user: { role: string } }) => unknown) =>
    selector({ user: { role } }),
}));
vi.mock("../components/Markdown", () => ({
  default: ({ source }: { source: string }) => <div>{source}</div>,
}));

beforeEach(() => {
  getMock.mockReset();
  getMock.mockResolvedValue({
    data: [{ id: "p1", titulo: "Petição padrão", categoria: "peticao" }],
  });
});

describe("Biblioteca de Prompts — botões por papel (E7)", () => {
  it("excluir é privativo de superadmin/admin/socio", () => {
    expect([...PAPEIS_EXCLUIR_PROMPT].sort()).toEqual([
      "admin",
      "socio",
      "superadmin",
    ]);
  });

  it("estagiário não vê o botão de excluir", async () => {
    role = "estagiario";
    render(<Prompts />);
    await screen.findByText("Petição padrão");
    expect(screen.queryByRole("button", { name: /Excluir prompt/ })).toBeNull();
  });

  it("sócio vê o botão de excluir", async () => {
    role = "socio";
    render(<Prompts />);
    await screen.findByText("Petição padrão");
    expect(screen.getByRole("button", { name: /Excluir prompt/ })).toBeTruthy();
  });

  it("falha de carga vira ErrorState (S7)", async () => {
    getMock.mockRejectedValueOnce(new Error("rede"));
    render(<Prompts />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Não foi possível carregar os prompts/,
    );
  });
});
