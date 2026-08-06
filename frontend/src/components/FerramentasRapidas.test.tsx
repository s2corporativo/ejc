// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import FerramentasRapidas, { ATALHOS_FERRAMENTAS } from "./FerramentasRapidas";

afterEach(cleanup);

function renderizar(role?: string) {
  return render(
    <MemoryRouter>
      <FerramentasRapidas role={role} />
    </MemoryRouter>,
  );
}

describe("FerramentasRapidas (Dashboard — Issue #648)", () => {
  it("renderiza a seção para papel advogado com os 6 atalhos", () => {
    renderizar("advogado");
    expect(screen.getByText("Ferramentas jurídicas")).toBeTruthy();
    expect(screen.getAllByRole("link")).toHaveLength(6);
    expect(screen.getByText("Cálculo trabalhista")).toBeTruthy();
    expect(screen.getByText("Juros bancários")).toBeTruthy();
    expect(screen.getByText("Análise tributária")).toBeTruthy();
    expect(screen.getByText("Multas de trânsito")).toBeTruthy();
    expect(screen.getByText("Análise de contrato")).toBeTruthy();
    expect(screen.getByText("Todas as ferramentas")).toBeTruthy();
  });

  it("renderiza para os demais papéis do jurídico (estagiário)", () => {
    renderizar("estagiario");
    expect(screen.getByText("Ferramentas jurídicas")).toBeTruthy();
  });

  it("esconde a seção para papel sem acesso a /areas-de-atuacao", () => {
    for (const role of ["financeiro", "secretaria", undefined]) {
      const { container } = renderizar(role);
      expect(container.innerHTML).toBe("");
      cleanup();
    }
  });

  it("links apontam para os destinos certos (hubs de ramo + ferramentas)", () => {
    renderizar("advogado");
    const hrefPorTitulo = (titulo: string) =>
      screen.getByText(titulo).closest("a")?.getAttribute("href");

    expect(hrefPorTitulo("Cálculo trabalhista")).toBe(
      "/areas-de-atuacao/trabalhista",
    );
    expect(hrefPorTitulo("Juros bancários")).toBe("/areas-de-atuacao/bancario");
    expect(hrefPorTitulo("Análise tributária")).toBe(
      "/areas-de-atuacao/tributario",
    );
    expect(hrefPorTitulo("Multas de trânsito")).toBe(
      "/areas-de-atuacao/transito",
    );
    expect(hrefPorTitulo("Análise de contrato")).toBe(
      "/ferramentas?abrir=defesas",
    );
    expect(hrefPorTitulo("Todas as ferramentas")).toBe("/areas-de-atuacao");
  });

  it("todos os destinos de hub usam a rota canônica /areas-de-atuacao", () => {
    const hubs = ATALHOS_FERRAMENTAS.filter((atalho) =>
      atalho.destino.startsWith("/areas-de-atuacao/"),
    );
    expect(hubs.length).toBe(4);
    for (const hub of hubs) {
      expect(hub.destino).toMatch(/^\/areas-de-atuacao\/[a-z_]+$/);
    }
  });
});
