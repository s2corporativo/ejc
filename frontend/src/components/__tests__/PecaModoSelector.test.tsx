import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PecaModoSelector from "../PecaModoSelector";
import type { PecaModoMeta } from "../../types/pecaWorkflow";

const MODOS: PecaModoMeta[] = [
  {
    value: "livre",
    label: "Livre",
    descricao: "Instrução direta do advogado.",
    exige_caso: false,
    exige_aprovacao: false,
  },
  {
    value: "guiado",
    label: "Guiado",
    descricao: "Formulário estruturado por peça.",
    exige_caso: false,
    exige_aprovacao: false,
  },
  {
    value: "molde",
    label: "Molde",
    descricao: "Estrutura versionada do escritório.",
    exige_caso: false,
    exige_aprovacao: false,
  },
  {
    value: "agente",
    label: "Agente",
    descricao: "Plano com aprovação antes da redação.",
    exige_caso: true,
    exige_aprovacao: true,
  },
];

describe("PecaModoSelector", () => {
  it("exibe os quatro modos e marca o selecionado", () => {
    render(
      <PecaModoSelector modos={MODOS} value="livre" onChange={vi.fn()} />,
    );

    expect(screen.getByRole("button", { name: "Modo Livre" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Modo Guiado" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Modo Molde" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Modo Agente" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Modo Livre" }).getAttribute(
        "aria-pressed",
      ),
    ).toBe("true");
  });

  it("altera para um modo disponível", () => {
    const onChange = vi.fn();
    render(
      <PecaModoSelector
        modos={MODOS}
        value="livre"
        onChange={onChange}
        caseId="caso-1"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Modo Guiado" }));

    expect(onChange).toHaveBeenCalledWith("guiado");
  });

  it("bloqueia o Modo Agente quando não há caso vinculado", () => {
    const onChange = vi.fn();
    render(
      <PecaModoSelector modos={MODOS} value="livre" onChange={onChange} />,
    );

    const agente = screen.getByRole("button", { name: "Modo Agente" });
    expect((agente as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Vincule um caso para usar")).toBeTruthy();

    fireEvent.click(agente);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("libera o Agente com caso e sinaliza aprovação obrigatória", () => {
    render(
      <PecaModoSelector
        modos={MODOS}
        value="agente"
        onChange={vi.fn()}
        caseId="caso-1"
      />,
    );

    const agente = screen.getByRole("button", { name: "Modo Agente" });
    expect((agente as HTMLButtonElement).disabled).toBe(false);
    expect(agente.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("Aprovação antes da redação")).toBeTruthy();
  });
});
