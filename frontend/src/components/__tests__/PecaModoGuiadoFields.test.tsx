import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PecaModoGuiadoFields from "../PecaModoGuiadoFields";

describe("PecaModoGuiadoFields", () => {
  it("renderiza somente os campos informados pelo backend", () => {
    render(
      <PecaModoGuiadoFields
        campos={["fatos_impugnados", "provas_defesa", "pedidos"]}
        value={{}}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("textbox", { name: "Fatos impugnados" })).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Provas defesa" })).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Pedidos" })).toBeTruthy();
    expect(screen.getByText("0 de 3 preenchidos")).toBeTruthy();
  });

  it("preserva as respostas existentes ao alterar um campo", () => {
    const onChange = vi.fn();
    render(
      <PecaModoGuiadoFields
        campos={["fatos", "pedidos"]}
        value={{ fatos: "Fato confirmado", pedidos: "" }}
        onChange={onChange}
      />,
    );

    fireEvent.change(screen.getByRole("textbox", { name: "Pedidos" }), {
      target: { value: "Improcedência dos pedidos." },
    });

    expect(onChange).toHaveBeenCalledWith({
      fatos: "Fato confirmado",
      pedidos: "Improcedência dos pedidos.",
    });
    expect(screen.getByText("1 de 2 preenchidos")).toBeTruthy();
  });

  it("bloqueia os campos durante preparação ou geração", () => {
    render(
      <PecaModoGuiadoFields
        campos={["fatos"]}
        value={{}}
        onChange={vi.fn()}
        disabled
      />,
    );

    expect(
      (screen.getByRole("textbox", { name: "Fatos" }) as HTMLTextAreaElement)
        .disabled,
    ).toBe(true);
  });

  it("falha de forma segura quando o catálogo não informa campos", () => {
    render(
      <PecaModoGuiadoFields campos={[]} value={{}} onChange={vi.fn()} />,
    );

    expect(
      screen.getByText(/backend não informou campos guiados/i),
    ).toBeTruthy();
    expect(screen.queryAllByRole("textbox")).toHaveLength(0);
  });
});
