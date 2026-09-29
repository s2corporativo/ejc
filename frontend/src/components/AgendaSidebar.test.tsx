// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { addMonths, format } from "date-fns";
import { ptBR } from "date-fns/locale";
import AgendaSidebar from "./AgendaSidebar";

const getMock = vi.fn();

vi.mock("../lib/api", () => ({
  default: { get: (...args: unknown[]) => getMock(...args) },
}));

const HOJE = new Date();
const CHAVE_HOJE = format(HOJE, "yyyy-MM-dd");
const ROTULO_HOJE = format(HOJE, "EEEE, dd 'de' MMMM", { locale: ptBR });
const ROTULO_MES = format(HOJE, "MMMM 'de' yyyy", { locale: ptBR });

/** Atividades padrão: uma com caso vinculado, outra sem, ambas hoje. */
function payload() {
  return {
    data: [
      {
        id: "ativ-1",
        tipo: "prazo",
        titulo: "Audiência trabalhista",
        date: CHAVE_HOJE,
        case_id: "caso-1",
        caso_titulo: "Processo principal",
      },
      {
        id: "ativ-2",
        tipo: "tarefa",
        titulo: "Minutar peça",
        date: CHAVE_HOJE,
        case_id: null,
        caso_titulo: null,
      },
    ],
  };
}

function renderAgenda(navCollapsed = false) {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route
          path="*"
          element={<AgendaSidebar navCollapsed={navCollapsed} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  getMock.mockReset();
  getMock.mockResolvedValue(payload());
});

afterEach(cleanup);

describe("AgendaSidebar — calendário da agenda na sidebar", () => {
  it("consulta /atividades sem filtrar pendentes e monta a grade do mês", async () => {
    renderAgenda();

    await waitFor(() => expect(getMock).toHaveBeenCalled());
    expect(getMock).toHaveBeenCalledWith("/atividades", {
      params: { apenas_pendentes: false },
    });
    expect(screen.getByRole("grid", { name: "Calendário do mês" })).toBeTruthy();
    expect(screen.getByText(ROTULO_MES)).toBeTruthy();
  });

  it("desempacota o envelope { data: [] } em vez de esperar array cru", async () => {
    renderAgenda();
    await waitFor(() =>
      expect(screen.getByLabelText(`${ROTULO_HOJE} — 2 itens`)).toBeTruthy(),
    );
  });

  it("rotula cada dia por extenso, nunca só pelo número, e sem repetição", async () => {
    renderAgenda();
    await waitFor(() => expect(getMock).toHaveBeenCalled());

    const celulas = screen.getAllByRole("gridcell");
    expect(celulas.length).toBeGreaterThanOrEqual(28);
    expect(celulas.length).toBeLessThanOrEqual(42);
    const rotulos: string[] = [];
    for (const celula of celulas) {
      const rotulo = celula.getAttribute("aria-label") ?? "";
      expect(rotulo).toMatch(
        /^(segunda|terça|quarta|quinta|sexta|sábado|domingo)(-feira)?, \d{2} de /,
      );
      rotulos.push(rotulo);
    }
    expect(new Set(rotulos).size).toBe(rotulos.length);
  });

  it("mantém um único tab stop na grade (roving tabindex)", async () => {
    renderAgenda();
    await waitFor(() => expect(getMock).toHaveBeenCalled());

    const tabulaveis = screen
      .getAllByRole("gridcell")
      .filter((c) => c.getAttribute("tabindex") === "0");
    expect(tabulaveis).toHaveLength(1);
  });

  it("navega entre meses pelos botões do cabeçalho", async () => {
    renderAgenda();
    await waitFor(() => expect(getMock).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Próximo mês" }));
    expect(
      screen.getByText(
        format(addMonths(HOJE, 1), "MMMM 'de' yyyy", { locale: ptBR }),
      ),
    ).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Mês anterior" }));
    expect(screen.getByText(ROTULO_MES)).toBeTruthy();
  });

  it("volta ao mês corrente pelo botão 'Ir para hoje'", async () => {
    renderAgenda();
    await waitFor(() => expect(getMock).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Mês anterior" }));
    fireEvent.click(screen.getByRole("button", { name: "Ir para hoje" }));
    expect(screen.getByText(ROTULO_MES)).toBeTruthy();
  });

  it("mostra erro com 'Tentar novamente' e recarrega ao clicar", async () => {
    getMock.mockRejectedValue({ response: { status: 503 } });
    renderAgenda();

    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.queryByRole("grid")).toBeNull();

    const botao = screen.getByRole("button", { name: "Tentar novamente" });
    getMock.mockResolvedValue(payload());
    fireEvent.click(botao);

    await waitFor(() =>
      expect(
        screen.getByRole("grid", { name: "Calendário do mês" }),
      ).toBeTruthy(),
    );
  });

  it("abre a lista inline do dia com Enter e a fecha com Esc", async () => {
    renderAgenda();
    await waitFor(() => expect(getMock).toHaveBeenCalled());

    const hoje = screen.getByLabelText(`${ROTULO_HOJE} — 2 itens`);
    fireEvent.keyDown(hoje, { key: "Enter" });
    expect(screen.getByText("Audiência trabalhista")).toBeTruthy();

    fireEvent.keyDown(hoje, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByText("Audiência trabalhista")).toBeNull(),
    );
  });

  it("leva ao caso quando há case_id e à agenda do dia quando não há", async () => {
    renderAgenda();
    await waitFor(() => expect(getMock).toHaveBeenCalled());

    fireEvent.click(screen.getByLabelText(`${ROTULO_HOJE} — 2 itens`));
    expect(
      screen
        .getByRole("link", { name: /Audiência trabalhista/ })
        .getAttribute("href"),
    ).toBe("/casos/caso-1");
    expect(
      screen.getByRole("link", { name: /Minutar peça/ }).getAttribute("href"),
    ).toBe(`/atividades/dia/${CHAVE_HOJE}`);
  });

  it("diz que o dia está vazio em vez de fingir zero", async () => {
    getMock.mockResolvedValue({ data: [] });
    renderAgenda();
    await waitFor(() => expect(getMock).toHaveBeenCalled());

    // Primeiro dia do mês visível que não seja hoje — nunca terá itens.
    const diaVazio = new Date(
      HOJE.getFullYear(),
      HOJE.getMonth(),
      HOJE.getDate() === 1 ? 2 : 1,
    );
    fireEvent.click(
      screen.getByLabelText(
        `${format(diaVazio, "EEEE, dd 'de' MMMM", { locale: ptBR })} — sem itens`,
      ),
    );
    expect(screen.getByText("Nenhum item nesta data.")).toBeTruthy();
  });

  it("colapsada mostra só o ícone dourado levando a /atividades", async () => {
    renderAgenda(true);
    await waitFor(() => expect(getMock).toHaveBeenCalled());

    expect(screen.queryByRole("grid")).toBeNull();
    expect(
      screen
        .getByRole("link", { name: "Abrir a agenda do escritório" })
        .getAttribute("href"),
    ).toBe("/atividades");
  });
});
