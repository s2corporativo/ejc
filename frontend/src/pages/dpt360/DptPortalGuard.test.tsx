// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import DptPortalGuard from "./DptPortalGuard";

function renderGuard() {
  return render(
    <MemoryRouter>
      <DptPortalGuard />
    </MemoryRouter>,
  );
}

describe("DptPortalGuard", () => {
  it("exibe o título do compartilhamento com cliente", () => {
    renderGuard();
    screen.getByText("Compartilhamento com cliente");
  });

  it("documenta que rascunhos não são publicados diretamente", () => {
    renderGuard();
    screen.getByText(/O DPT não publica rascunhos diretamente/);
  });

  it("registra que publicação externa exige ato explícito no Data Room", () => {
    renderGuard();
    screen.getByText(/publicação externa exige ato explícito/i);
  });

  it("linka para o Data Room canônico", () => {
    renderGuard();
    const link = screen.getByRole("link", { name: /Abrir Data Room canônico/i });
    expect(link.getAttribute("href")).toBe("/data-room");
  });
});
