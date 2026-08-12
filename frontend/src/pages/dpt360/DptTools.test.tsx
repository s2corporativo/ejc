// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import DptTools from "./DptTools";

describe("DptTools", () => {
  it("lista todas as áreas de ferramentas", () => {
    render(
      <MemoryRouter>
        <DptTools />
      </MemoryRouter>,
    );
    screen.getByText("Tributário");
    screen.getByText("Ambiental");
    screen.getByText("LGPD");
    screen.getByText("Governança de IA");
  });

  it("marca as ferramentas como disponíveis", () => {
    render(
      <MemoryRouter>
        <DptTools />
      </MemoryRouter>,
    );
    // Nenhuma ferramenta aparece como indisponível; os ícones de
    // verificação verde têm aria-hidden e o texto fica em sr-only.
    expect(screen.queryByRole("img", { name: "Indisponível", hidden: true })).toBeNull();
  });

  it("apresenta a evidência de backend por área", () => {
    render(
      <MemoryRouter>
        <DptTools />
      </MemoryRouter>,
    );
    screen.getByText(/Backend confirmado: \/api\/tributario\/fiscal\//);
    screen.getByText(/Backend confirmado: \/api\/lgpd\/registros\//);
  });

  it("linka cada área para seu workspace canônico", () => {
    render(
      <MemoryRouter>
        <DptTools />
      </MemoryRouter>,
    );
    const links = screen.getAllByRole("link", {
      name: /Abrir workspace canônico/i,
    });
    const hrefs = links.map((link) => link.getAttribute("href"));
    expect(hrefs).toContain("/areas-de-atuacao/tributario");
    expect(hrefs).toContain("/areas-de-atuacao/ambiental");
    expect(hrefs).toContain("/areas-de-atuacao/digital_lgpd");
  });
});
