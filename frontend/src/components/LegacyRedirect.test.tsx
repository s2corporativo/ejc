// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import LegacyRedirect, { mesclarDestinoLegado } from "./LegacyRedirect";

afterEach(cleanup);

describe("mesclarDestinoLegado — FLX-029 (query preservada no redirect legado)", () => {
  it("mescla a query de origem com a query embutida no destino", () => {
    const destino = mesclarDestinoLegado(
      "/atividades?tipo=prazo",
      "?caso=c1",
      "",
    );
    const url = new URL(destino, "http://local");
    expect(url.pathname).toBe("/atividades");
    expect(url.searchParams.get("tipo")).toBe("prazo");
    expect(url.searchParams.get("caso")).toBe("c1");
  });

  it("em conflito, o param embutido no destino vence", () => {
    const destino = mesclarDestinoLegado(
      "/atividades?tipo=prazo",
      "?tipo=tarefa&caso=c1",
      "",
    );
    const url = new URL(destino, "http://local");
    expect(url.searchParams.getAll("tipo")).toEqual(["prazo"]);
    expect(url.searchParams.get("caso")).toBe("c1");
  });

  it("destino sem query herda a query e o hash de origem", () => {
    expect(
      mesclarDestinoLegado("/areas-de-atuacao", "?foco=civil", "#topo"),
    ).toBe("/areas-de-atuacao?foco=civil#topo");
  });

  it("sem query de origem, mantém o destino como está", () => {
    expect(mesclarDestinoLegado("/atividades?tipo=prazo", "", "")).toBe(
      "/atividades?tipo=prazo",
    );
  });
});

function EcoLocalizacao() {
  const location = useLocation();
  return <div data-testid="destino">{location.pathname + location.search}</div>;
}

describe("LegacyRedirect (render)", () => {
  it("redireciona /prazos?caso=c1 para /atividades com tipo=prazo E caso=c1", () => {
    render(
      <MemoryRouter initialEntries={["/prazos?caso=c1"]}>
        <Routes>
          <Route
            path="/prazos"
            element={<LegacyRedirect to="/atividades?tipo=prazo" />}
          />
          <Route path="/atividades" element={<EcoLocalizacao />} />
        </Routes>
      </MemoryRouter>,
    );
    const destino = screen.getByTestId("destino").textContent ?? "";
    const url = new URL(destino, "http://local");
    expect(url.pathname).toBe("/atividades");
    expect(url.searchParams.get("tipo")).toBe("prazo");
    expect(url.searchParams.get("caso")).toBe("c1");
  });
});
