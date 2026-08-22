// @vitest-environment jsdom
// Achado P1 da revisão do Codex em 2026-08-22 (PR #1238).
//
// `FeeCreate` passou a exigir `valor` OU `percentual_exito` — correção do
// honorário que nascia sem dizer quanto cobrar. Só que o formulário oferecia
// apenas "Valor (R$)". O contrato de êxito puramente percentual, que o schema
// declara suportar e que é o arranjo mais comum em ação indenizatória, ficou
// impossível pela interface: ou o advogado batia num 422, ou inventava um
// valor fixo — e aí o registro passa a dizer outra coisa sobre o contrato.
//
// Uma validação de backend que fecha um caminho legítimo porque a tela não
// tem o campo correspondente não é uma correção completa.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";

const get = vi.fn();
const post = vi.fn();
vi.mock("../lib/api", () => ({
  default: {
    get: (...a: unknown[]) => get(...a),
    post: (...a: unknown[]) => post(...a),
  },
}));
vi.mock("../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock("qrcode", () => ({ default: { toDataURL: vi.fn() } }));

import Honorarios from "./Honorarios";

const CLIENTE = { id: "c1", nome: "Cliente Teste" };

function montar() {
  return render(
    <MemoryRouter>
      <Honorarios />
    </MemoryRouter>,
  );
}

describe("Honorários — contrato de êxito puramente percentual", () => {
  beforeEach(() => {
    get.mockImplementation((url: string) => {
      if (url.startsWith("/clients")) {
        return Promise.resolve({ data: { data: [CLIENTE] } });
      }
      return Promise.resolve({ data: { data: [], total: 0 } });
    });
    post.mockResolvedValue({ data: { id: "f1" } });
  });
  afterEach(() => {
    cleanup();
    get.mockReset();
    post.mockReset();
  });

  it("o formulário oferece o campo de percentual de êxito", async () => {
    montar();
    fireEvent.click(await screen.findByText("Novo lançamento"));
    // Antes da correção este campo não existia e o único jeito de salvar um
    // contrato de êxito era preencher um valor fixo que não era o contratado.
    expect(screen.getByText("Percentual de êxito (%)")).toBeTruthy();
  });

  it("salva com percentual e sem valor, sem mandar string vazia", async () => {
    montar();
    fireEvent.click(await screen.findByText("Novo lançamento"));

    const campo = (rotulo: string) =>
      screen
        .getByText(rotulo)
        .parentElement!.querySelector("input, select") as HTMLInputElement;

    fireEvent.change(campo("Descrição *"), {
      target: { value: "Êxito 20% sobre a condenação" },
    });
    fireEvent.change(campo("Cliente *"), { target: { value: "c1" } });
    fireEvent.change(campo("Percentual de êxito (%)"), {
      target: { value: "20" },
    });
    // "Valor (R$)" fica vazio de propósito: é o caso que estava bloqueado.
    fireEvent.click(screen.getByText("Lançar"));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    const [rota, corpo] = post.mock.calls[0] as [
      string,
      Record<string, unknown>,
    ];
    expect(rota).toBe("/fees/");
    expect(corpo.percentual_exito).toBe("20");
    // String vazia num campo numérico faz o Pydantic responder "Input should be
    // a valid decimal" — erro de digitação, quando a regra é outra. O payload
    // não pode carregar o campo vazio.
    expect(corpo.valor).toBeUndefined();
  });

  it("descrição e cliente continuam obrigatórios antes de chamar a API", async () => {
    montar();
    fireEvent.click(await screen.findByText("Novo lançamento"));
    fireEvent.click(screen.getByText("Lançar"));
    await waitFor(() => expect(post).not.toHaveBeenCalled());
  });
});
