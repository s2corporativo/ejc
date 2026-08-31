// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import JurisprudentialAlertsStrip from "./JurisprudentialAlertsStrip";

describe("JurisprudentialAlertsStrip", () => {
  it("exibe os dois alertas jurídicos curados e preserva revisão humana", () => {
    render(
      <MemoryRouter>
        <JurisprudentialAlertsStrip />
      </MemoryRouter>,
    );

    expect(screen.getByText(/Tema 1\.469/i)).toBeTruthy();
    expect(screen.getByText(/Acórdão 2218\/2026-Plenário/i)).toBeTruthy();
    expect(screen.getByText(/revisão humana obrigatória/i)).toBeTruthy();
    expect(
      screen.getByText(/Nenhum aviso altera automaticamente tese/i),
    ).toBeTruthy();
  });

  it("leva o usuário ao Radar Jurídico canônico", () => {
    render(
      <MemoryRouter>
        <JurisprudentialAlertsStrip />
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: /Abrir Radar Jurídico/i });
    expect(link.getAttribute("href")).toBe("/dpt360/radar");
  });

  it("mantém as fontes oficiais disponíveis para auditoria", () => {
    render(
      <MemoryRouter>
        <JurisprudentialAlertsStrip />
      </MemoryRouter>,
    );

    const fontes = screen.getAllByRole("link", { name: /Fonte oficial/i });
    expect(fontes).toHaveLength(2);
    expect(fontes[0].getAttribute("href")).toContain("stj.jus.br");
    expect(fontes[1].getAttribute("href")).toContain("tcu.gov.br");
  });
});
