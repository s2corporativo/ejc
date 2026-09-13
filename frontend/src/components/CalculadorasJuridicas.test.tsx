// @vitest-environment jsdom
// V2-5.1 (plano-mestre): a auditoria encontrou ~50 calculadoras jurídicas
// já implementadas no backend, nenhuma exposta em tela — esta é a primeira
// leva (6, de 4 cível + 2 penal). Form-runner genérico: os testes cobrem o
// comportamento do runner (form dinâmico, params, erro, campo condicional),
// não o resultado específico de cada endpoint.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const getMock = vi.fn();

vi.mock("../lib/api", () => ({
  default: {
    get: (...a: unknown[]) => getMock(...a),
  },
  getAccessToken: () => null,
  logout: vi.fn(),
  refreshAccessToken: vi.fn(),
}));

import CalculadorasJuridicas from "./CalculadorasJuridicas";

beforeEach(() => {
  getMock.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("CalculadorasJuridicas — lista e seleção", () => {
  it("lista as 6 ferramentas da primeira leva, agrupadas por área", () => {
    render(<CalculadorasJuridicas />);
    expect(screen.getByText("Cível")).toBeTruthy();
    expect(screen.getByText("Penal")).toBeTruthy();
    // "Prazo de contestação" está selecionada por padrão (aparece no chip E
    // no título do formulário) — as demais só no chip, getByText basta.
    expect(screen.getAllByText("Prazo de contestação").length).toBeGreaterThan(0);
    expect(screen.getByText("Cálculo de alimentos")).toBeTruthy();
    expect(screen.getByText("Verificação de usucapião")).toBeTruthy();
    expect(screen.getByText("Estruturação de dano moral")).toBeTruthy();
    expect(screen.getByText("Prazos do processo penal")).toBeTruthy();
    expect(screen.getByText("Elegibilidade ao ANPP")).toBeTruthy();
  });

  it("selecionar uma ferramenta renderiza os campos certos (ANPP: 7 campos)", () => {
    render(<CalculadorasJuridicas />);
    fireEvent.click(screen.getByText("Elegibilidade ao ANPP"));
    expect(screen.getByText("Pena mínima cominada (anos)")).toBeTruthy();
    expect(screen.getByText("Infração sem violência ou grave ameaça")).toBeTruthy();
    expect(screen.getByText("Confissão formal e circunstanciada")).toBeTruthy();
    expect(screen.getByText("É reincidente")).toBeTruthy();
    expect(
      screen.getByText("Conduta criminal habitual/reiterada/profissional"),
    ).toBeTruthy();
    expect(
      screen.getByText("Já beneficiado com ANPP/transação/sursis nos últimos 5 anos"),
    ).toBeTruthy();
    expect(
      screen.getByText("Violência doméstica/familiar ou razão de gênero"),
    ).toBeTruthy();
  });

  it("campo condicional: selecionar rito=jec esconde marco e data do marco", () => {
    render(<CalculadorasJuridicas />);
    // "Prazo de contestação" já vem selecionada por padrão (primeira da lista).
    expect(screen.getByText("Marco inicial")).toBeTruthy();
    const selectRito = screen.getByText("Rito").parentElement!.querySelector("select")!;
    fireEvent.change(selectRito, { target: { value: "jec" } });
    expect(screen.queryByText("Marco inicial")).toBeNull();
    expect(screen.queryByText("Data do marco")).toBeNull();
  });
});

describe("CalculadorasJuridicas — cálculo", () => {
  it("botão Calcular fica desabilitado até os campos obrigatórios serem preenchidos", () => {
    render(<CalculadorasJuridicas />);
    fireEvent.click(screen.getByText("Cálculo de alimentos"));
    const botao = screen.getByRole("button", { name: /calcular/i }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
  });

  it("chama a API com os params certos ao calcular", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        valor_mensal: 1500,
        fontes: ["CC arts. 1.694 §1º, 1.695 e 1.699"],
        aviso: "MINUTA de estimativa aritmética.",
      },
    });
    render(<CalculadorasJuridicas />);
    fireEvent.click(screen.getByText("Cálculo de alimentos"));

    const inputPorLabel = (label: string) =>
      screen.getByText(label).parentElement!.querySelector("input")!;
    fireEvent.change(inputPorLabel("Salário do devedor (R$)"), {
      target: { value: "5000" },
    });
    fireEvent.change(inputPorLabel("Percentual (%)"), { target: { value: "30" } });

    const botao = screen.getByRole("button", { name: /calcular/i }) as HTMLButtonElement;
    expect(botao.disabled).toBe(false);
    fireEvent.click(botao);

    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(1));
    expect(getMock).toHaveBeenCalledWith("/civel/ferramentas/alimentos-calcular", {
      params: { salario_devedor: 5000, percentual: 30, filhos: 1 },
    });
  });

  it("renderiza aviso e fontes no resultado", async () => {
    getMock.mockResolvedValueOnce({
      data: {
        valor_mensal: 1500,
        fontes: ["CC arts. 1.694 §1º, 1.695 e 1.699"],
        aviso: "MINUTA de estimativa aritmética.",
      },
    });
    render(<CalculadorasJuridicas />);
    fireEvent.click(screen.getByText("Cálculo de alimentos"));
    const inputPorLabel = (label: string) =>
      screen.getByText(label).parentElement!.querySelector("input")!;
    fireEvent.change(inputPorLabel("Salário do devedor (R$)"), {
      target: { value: "5000" },
    });
    fireEvent.change(inputPorLabel("Percentual (%)"), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: /calcular/i }));

    await waitFor(() =>
      expect(screen.getByText("MINUTA de estimativa aritmética.")).toBeTruthy(),
    );
    expect(screen.getByText("CC arts. 1.694 §1º, 1.695 e 1.699")).toBeTruthy();
  });

  it("trata erro 422 com detail em string", async () => {
    getMock.mockRejectedValueOnce({
      response: { data: { detail: "Rito inválido. Use: comum | jec | fazenda_publica" } },
    });
    render(<CalculadorasJuridicas />);
    fireEvent.click(screen.getByText("Prazos do processo penal"));
    const inputData = screen
      .getByText("Data da citação")
      .parentElement!.querySelector("input")!;
    fireEvent.change(inputData, { target: { value: "2026-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: /calcular/i }));

    await waitFor(() =>
      expect(
        screen.getByText("Rito inválido. Use: comum | jec | fazenda_publica"),
      ).toBeTruthy(),
    );
  });

  it("trata erro 422 com detail em array (validação Pydantic)", async () => {
    getMock.mockRejectedValueOnce({
      response: { data: { detail: [{ msg: "ensure this value is greater than 0" }] } },
    });
    render(<CalculadorasJuridicas />);
    fireEvent.click(screen.getByText("Prazos do processo penal"));
    const inputData = screen
      .getByText("Data da citação")
      .parentElement!.querySelector("input")!;
    fireEvent.change(inputData, { target: { value: "2026-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: /calcular/i }));

    await waitFor(() =>
      expect(
        screen.getByText("ensure this value is greater than 0"),
      ).toBeTruthy(),
    );
  });
});
