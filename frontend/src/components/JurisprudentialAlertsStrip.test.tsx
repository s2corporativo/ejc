// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import JurisprudentialAlertsStrip from "./JurisprudentialAlertsStrip";

describe("JurisprudentialAlertsStrip", () => {
  it("exibe as cinco atualizações jurídicas curadas da semana", () => {
    render(
      <MemoryRouter>
        <JurisprudentialAlertsStrip />
      </MemoryRouter>,
    );

    expect(screen.getByText(/Tema 1\.177/i)).toBeTruthy();
    expect(screen.getByText(/Tema 1\.473/i)).toBeTruthy();
    expect(screen.getByText(/Acórdão 2321\/2026-Plenário/i)).toBeTruthy();
    expect(screen.getByText(/Decreto 13\.108\/2026/i)).toBeTruthy();
    expect(screen.getByText(/Decreto 13\.109\/2026/i)).toBeTruthy();
    expect(screen.getByText("5")).toBeTruthy();
    expect(
      screen.getByRole("feed", { name: /Atualizações jurídicas/i }),
    ).toBeTruthy();
  });

  it("preserva o gate de revisão humana", () => {
    render(
      <MemoryRouter>
        <JurisprudentialAlertsStrip />
      </MemoryRouter>,
    );

    expect(
      screen.getByText(
        /Nenhum item altera tese, caso ou peça sem validação humana/i,
      ),
    ).toBeTruthy();
    expect(screen.getAllByText(/Impacto e ação recomendada/i)).toHaveLength(5);
  });

  it("leva ao Radar Jurídico canônico", () => {
    render(
      <MemoryRouter>
        <JurisprudentialAlertsStrip />
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: /Abrir radar/i });
    expect(link.getAttribute("href")).toBe("/dpt360/radar");
  });

  it("mantém todas as fontes oficiais disponíveis para auditoria", () => {
    render(
      <MemoryRouter>
        <JurisprudentialAlertsStrip />
      </MemoryRouter>,
    );

    const fontes = screen.getAllByRole("link", { name: /Fonte oficial/i });
    expect(fontes).toHaveLength(5);
    expect(fontes[0].getAttribute("href")).toContain("stj.jus.br");
    expect(fontes[1].getAttribute("href")).toContain("stj.jus.br");
    expect(fontes[2].getAttribute("href")).toContain("tcu.gov.br");
    expect(fontes[3].getAttribute("href")).toContain("planalto.gov.br");
    expect(fontes[4].getAttribute("href")).toContain("planalto.gov.br");
  });
});
