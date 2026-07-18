import { useState } from "react";
import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import LegacyActivityQueryAdapter from "../LegacyActivityQueryAdapter";

function FakeFilters() {
  const [active, setActive] = useState("Todos");
  return (
    <div>
      {["Todos", "Prazo", "Tarefa"].map((label) => (
        <button
          key={label}
          type="button"
          onClick={() => setActive(label)}
          className={active === label ? "bg-navy text-white" : "bg-slate-100"}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

describe("LegacyActivityQueryAdapter", () => {
  it("ativa o filtro solicitado por ?tipo=", async () => {
    render(
      <MemoryRouter initialEntries={["/atividades?tipo=prazo"]}>
        <LegacyActivityQueryAdapter>
          <FakeFilters />
        </LegacyActivityQueryAdapter>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Prazo" }).className,
      ).toContain("bg-navy");
    });
  });

  it("ignora tipo desconhecido sem alterar o filtro atual", async () => {
    render(
      <MemoryRouter initialEntries={["/atividades?tipo=inexistente"]}>
        <LegacyActivityQueryAdapter>
          <FakeFilters />
        </LegacyActivityQueryAdapter>
      </MemoryRouter>,
    );

    await Promise.resolve();
    expect(screen.getByRole("button", { name: "Todos" }).className).toContain(
      "bg-navy",
    );
  });
});
