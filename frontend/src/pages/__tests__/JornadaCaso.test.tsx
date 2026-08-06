import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";

import JornadaCaso from "../JornadaCaso";

function DestinoProbe() {
  const { pathname, search } = useLocation();
  return <div>DESTINO:{`${pathname}${search}`}</div>;
}

describe("JornadaCaso — rota histórica redireciona para a Visão do caso", () => {
  it("responde ao deep-link /casos/:id/jornada redirecionando para ?tab=resumo", () => {
    render(
      <MemoryRouter initialEntries={["/casos/case-1/jornada"]}>
        <Routes>
          <Route path="/casos/:id/jornada" element={<JornadaCaso />} />
          <Route path="/casos/:id" element={<DestinoProbe />} />
        </Routes>
      </MemoryRouter>,
    );

    // Fase 1: a jornada vive embutida na Visão (aba resumo) — a rota antiga
    // não quebra favoritos, apenas leva ao destino novo.
    expect(screen.getByText("DESTINO:/casos/case-1?tab=resumo")).toBeTruthy();
  });
});
