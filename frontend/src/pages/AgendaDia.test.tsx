import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AgendaDia from "./AgendaDia";

const getMock = vi.fn();

vi.mock("../lib/api", () => ({
  default: {
    get: (...args: unknown[]) => getMock(...args),
  },
}));

function renderRoute(date: string) {
  render(
    <MemoryRouter initialEntries={[`/atividades/dia/${date}`]}>
      <Routes>
        <Route path="/atividades/dia/:date" element={<AgendaDia />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  getMock.mockReset();
});

describe("agenda diária", () => {
  it("exibe somente as atividades reais da data selecionada", async () => {
    getMock.mockImplementation((url: string) => {
      if (url === "/atividades") {
        return Promise.resolve({
          data: [
            {
              id: "atividade-1",
              tipo: "agenda",
              titulo: "Audiência trabalhista",
              date: "2026-08-05",
              status: "pendente",
              case_id: "caso-1",
              caso_titulo: "Processo principal",
            },
            {
              id: "atividade-2",
              tipo: "tarefa",
              titulo: "Atividade de outro dia",
              date: "2026-08-06",
              status: "a_fazer",
            },
          ],
        });
      }
      if (url === "/agenda-eventos/") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "atividade-1",
                tipo: "audiencia",
                hora: "09:30",
                local: "Fórum trabalhista",
              },
            ],
          },
        });
      }
      return Promise.reject(new Error(`URL inesperada: ${url}`));
    });

    renderRoute("2026-08-05");

    await waitFor(() => {
      expect(screen.getByText("Audiência trabalhista")).toBeTruthy();
    });
    expect(screen.queryByText("Atividade de outro dia")).toBeNull();
    expect(screen.getAllByText(/09:30/)).toHaveLength(2);
    expect(screen.getByText(/Fórum trabalhista/)).toBeTruthy();
    expect(getMock).toHaveBeenCalledWith("/atividades", {
      params: { apenas_pendentes: false },
    });
  });

  it("não consulta a API quando a data da rota é inválida", async () => {
    renderRoute("2026-99-99");

    expect(screen.getByText("A data informada não é válida.")).toBeTruthy();
    expect(getMock).not.toHaveBeenCalled();
  });

  it("mostra estado de erro sem inventar compromissos", async () => {
    getMock.mockRejectedValue(new Error("indisponível"));

    renderRoute("2026-08-05");

    await waitFor(() => {
      expect(
        screen.getByText("Não foi possível carregar a agenda deste dia."),
      ).toBeTruthy();
    });
    expect(screen.queryByText("Audiência trabalhista")).toBeNull();
  });
});
