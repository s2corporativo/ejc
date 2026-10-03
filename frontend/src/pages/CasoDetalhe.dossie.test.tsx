// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

const mocks = vi.hoisted(() => ({
  role: "advogado",
  montagensDossie: 0,
}));

vi.mock("../stores/auth", () => ({
  useAuth: (selector?: (state: unknown) => unknown) => {
    const state = { user: { id: "u1", role: mocks.role } };
    return selector ? selector(state) : state;
  },
}));

vi.mock("../components/DossieEstrategicoCaso", () => ({
  default: () => <p>dossiê estratégico</p>,
}));

// Montar o DossieJuridico real dispara POST /entrada/analisar (IA + snapshot).
vi.mock("./EntradaUnica/DossieJuridico", async () => {
  const { useEffect } = await import("react");
  return {
    default: () => {
      useEffect(() => {
        mocks.montagensDossie += 1;
      }, []);
      return <p>dossiê jurídico</p>;
    },
  };
});

import { DossieIntegradoCaso } from "./CasoDetalhe";

function renderDossie() {
  return render(
    <MemoryRouter>
      <DossieIntegradoCaso caseId="case-1" />
    </MemoryRouter>,
  );
}

describe("CasoDetalhe — Dossiê Jurídico sob demanda", () => {
  beforeEach(() => {
    mocks.role = "advogado";
    mocks.montagensDossie = 0;
  });

  afterEach(() => cleanup());

  it("alternar a visibilidade não remonta o dossiê (nem repete a análise de IA)", () => {
    renderDossie();
    expect(mocks.montagensDossie).toBe(0);

    fireEvent.click(
      screen.getByRole("button", { name: "Abrir Dossiê Jurídico" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Ocultar Dossiê Jurídico" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Abrir Dossiê Jurídico" }),
    );

    expect(mocks.montagensDossie).toBe(1);
    expect(screen.getByText("dossiê jurídico")).toBeTruthy();
  });

  it.each(["advogado_auxiliar", "estagiario", "secretaria"])(
    "não oferece o dossiê jurídico a %s (o endpoint exige advogado+)",
    (role) => {
      mocks.role = role;
      renderDossie();

      expect(screen.getByText("dossiê estratégico")).toBeTruthy();
      expect(
        screen.queryByRole("button", { name: "Abrir Dossiê Jurídico" }),
      ).toBeNull();
    },
  );
});
