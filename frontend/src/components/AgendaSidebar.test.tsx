// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { format } from "date-fns";

const getMock = vi.fn();
let rotaAtual = "/";

vi.mock("../lib/api", () => ({
  default: { get: (...args: unknown[]) => getMock(...args) },
}));

import AgendaSidebar from "./AgendaSidebar";

const hoje = format(new Date(), "yyyy-MM-dd");

/** Publica a rota corrente para as asserções de navegação. */
function LocationProbe() {
  const { pathname } = useLocation();
  useEffect(() => {
    rotaAtual = pathname;
  }, [pathname]);
  return null;
}

function Harness({ colapsado }: { colapsado?: boolean }) {
  return (
    <Routes>
      <Route
        path="*"
        element={
          <>
            <LocationProbe />
            <AgendaSidebar colapsado={colapsado} />
          </>
        }
      />
    </Routes>
  );
}

function montar(colapsado?: boolean) {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Harness colapsado={colapsado} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  rotaAtual = "/";
  getMock.mockReset();
});

afterEach(cleanup);

describe("AgendaSidebar", () => {
  it("renderiza o calendário do mês corrente e marca os dias com item", async () => {
    getMock.mockResolvedValue({
      data: {
        data: [
          {
            id: "a1",
            tipo: "prazo",
            titulo: "Prazo — Contestação",
            date: hoje,
            case_id: "c1",
            caso_titulo: "Ação de cobrança",
          },
        ],
      },
    });

    montar();

    await waitFor(() => expect(screen.getByRole("grid")).toBeTruthy());
    expect(screen.getByRole("heading", { name: /agenda/i })).toBeTruthy();
    expect(getMock).toHaveBeenCalledWith("/atividades", {
      params: { apenas_pendentes: false },
    });
    // A view entrega `date` como data pura; o widget compara por yyyy-MM-dd.
    expect(screen.getByTestId(`dia-${hoje}`).className).toContain(
      "is-com-itens",
    );
    expect(
      screen.getByTestId(`dia-${hoje}`).getAttribute("aria-label"),
    ).toContain("1 item");
  });

  it("não quebra com payload inesperado e diz que não há itens", async () => {
    getMock.mockResolvedValue({ data: { data: null } });
    montar();
    await waitFor(() =>
      expect(screen.getByText(/nenhum prazo ou compromisso/i)).toBeTruthy(),
    );
  });

  it("navega entre meses pelos botões do cabeçalho", async () => {
    getMock.mockResolvedValue({ data: { data: [] } });
    montar();
    await waitFor(() => expect(screen.getByRole("grid")).toBeTruthy());

    const rotulo = () => screen.getByRole("grid").getAttribute("aria-label");
    const antes = rotulo();
    fireEvent.click(screen.getByLabelText("Próximo mês"));
    expect(rotulo()).not.toBe(antes);
    fireEvent.click(screen.getByLabelText("Mês anterior"));
    expect(rotulo()).toBe(antes);
  });

  it("mostra erro com 'Tentar novamente' em vez de vazio quando a API falha", async () => {
    getMock.mockRejectedValue({ response: { status: 500 } });

    montar();

    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    // A falha NÃO pode aparecer como "nenhum prazo" — é o silêncio que a
    // auditoria apontou nos 17 `catch(() => {})`.
    expect(screen.queryByText(/nenhum prazo ou compromisso/i)).toBeNull();
    expect(screen.queryByRole("grid")).toBeNull();

    getMock.mockResolvedValue({ data: { data: [] } });
    fireEvent.click(screen.getByRole("button", { name: /tentar novamente/i }));
    await waitFor(() => expect(screen.getByRole("grid")).toBeTruthy());
  });

  it("403 vira mensagem de permissão, não erro genérico", async () => {
    getMock.mockRejectedValue({ response: { status: 403 } });
    montar();
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByText(/não tem permissão/i)).toBeTruthy();
  });

  it("ao clicar no dia, lista os itens e leva ao caso correspondente", async () => {
    getMock.mockResolvedValue({
      data: {
        data: [
          {
            id: "a1",
            tipo: "prazo",
            titulo: "Prazo — Contestação",
            date: hoje,
            case_id: "c1",
            caso_titulo: "Ação de cobrança",
          },
        ],
      },
    });

    montar();
    await waitFor(() => expect(screen.getByTestId(`dia-${hoje}`)).toBeTruthy());

    fireEvent.click(screen.getByTestId(`dia-${hoje}`));
    expect(screen.getByText("Prazo — Contestação")).toBeTruthy();
    expect(screen.getByText("Ação de cobrança")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /contestação/i }));
    expect(rotaAtual).toBe("/casos/c1");
  });

  it("sem case_id, o item abre a Agenda do Dia do registry", async () => {
    getMock.mockResolvedValue({
      data: { data: [{ id: "a2", titulo: "Reunião interna", date: hoje }] },
    });

    montar();
    await waitFor(() => expect(screen.getByTestId(`dia-${hoje}`)).toBeTruthy());
    fireEvent.click(screen.getByTestId(`dia-${hoje}`));
    fireEvent.click(screen.getByRole("button", { name: /reunião interna/i }));
    expect(rotaAtual).toBe(`/atividades/dia/${hoje}`);
  });

  it("usa travessia (roving tabindex) e navegação por teclado no grid", async () => {
    getMock.mockResolvedValue({ data: { data: [] } });
    montar();
    await waitFor(() => expect(screen.getByRole("grid")).toBeTruthy());

    // Sem dia selecionado, o único ponto de entrada na grade é hoje.
    expect(screen.getByTestId(`dia-${hoje}`).getAttribute("tabindex")).toBe("0");

    fireEvent.keyDown(screen.getByTestId(`dia-${hoje}`), { key: "ArrowRight" });

    // A seta move a seleção: exatamente um gridcell marcado.
    const selecionados = screen
      .getAllByRole("gridcell")
      .filter((c) => c.getAttribute("aria-selected") === "true");
    expect(selecionados).toHaveLength(1);
    expect(selecionados[0].getAttribute("data-dia")).not.toBe(hoje);
    expect(selecionados[0].getAttribute("tabindex")).toBe("0");
  });

  it("Esc fecha a lista do dia", async () => {
    getMock.mockResolvedValue({
      data: { data: [{ id: "a1", titulo: "Prazo", date: hoje }] },
    });
    montar();
    await waitFor(() => expect(screen.getByTestId(`dia-${hoje}`)).toBeTruthy());
    fireEvent.click(screen.getByTestId(`dia-${hoje}`));
    expect(screen.getByText("Prazo")).toBeTruthy();
    fireEvent.keyDown(screen.getByTestId(`dia-${hoje}`), { key: "Escape" });
    expect(screen.queryByText("Prazo")).toBeNull();
  });

  it("colapsado, vira um único botão que leva a Prazos e Agenda", async () => {
    getMock.mockResolvedValue({ data: { data: [] } });
    montar(true);
    expect(screen.queryByRole("grid")).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: /abrir prazos e agenda/i }),
    );
    await waitFor(() => expect(rotaAtual).toBe("/atividades"));
  });

  it("campo ausente mostra '—', nunca string vazia nem zero falso", async () => {
    getMock.mockResolvedValue({
      data: { data: [{ id: "a3", titulo: "", date: hoje, case_id: "c9" }] },
    });
    montar();
    await waitFor(() => expect(screen.getByTestId(`dia-${hoje}`)).toBeTruthy());
    fireEvent.click(screen.getByTestId(`dia-${hoje}`));
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
