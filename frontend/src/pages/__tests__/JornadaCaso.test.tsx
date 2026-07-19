import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../../components/CaseBreadcrumb", () => ({
  default: () => <div>TRILHA_DO_CASO</div>,
}));

vi.mock("../../components/OrquestradorPanel", () => ({
  default: ({ caseId }: { caseId: string }) => (
    <div>ORQUESTRADOR_OFICIAL:{caseId}</div>
  ),
}));

import JornadaCaso from "../JornadaCaso";

describe("JornadaCaso — fonte única no Orquestrador", () => {
  it("reutiliza o painel oficial com o id do caso e preserva o deep-link", () => {
    render(
      <MemoryRouter initialEntries={["/casos/case-1/jornada"]}>
        <Routes>
          <Route path="/casos/:id/jornada" element={<JornadaCaso />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("ORQUESTRADOR_OFICIAL:case-1")).toBeTruthy();
    expect(screen.getByText("Jornada do Caso")).toBeTruthy();
    const link = screen.getByRole("link", { name: /Abrir no caso/ });
    expect(link.getAttribute("href")).toBe("/casos/case-1?tab=orquestrador");
  });
});
