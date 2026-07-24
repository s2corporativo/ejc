import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const { get, toastError } = vi.hoisted(() => ({
  get: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("../../../lib/api", () => ({
  default: { get },
}));

vi.mock("../../Toast", () => ({
  toast: { error: toastError },
}));

import LinhaDoTempoProcessual from "../LinhaDoTempoProcessual";

const timeline = {
  case_id: "case-1",
  fase_atual: "conhecimento",
  fases: [
    { fase: "pre_processual", label: "Pré-processual", status: "concluida" },
    { fase: "conhecimento", label: "Conhecimento", status: "atual" },
  ],
  eventos: [
    {
      data: "2026-07-20",
      categoria: "movimento",
      tipo: "andamento",
      descricao: "Contestação juntada",
    },
  ],
  proximos_passos: [],
  estagnacao: { dias_parado: 3, nivel: "ok" },
};

const timesheet = {
  data: [
    {
      id: "time-1",
      data: "2026-07-21",
      minutos: 90,
      descricao: "Revisão da contestação",
      faturavel: true,
      faturada: false,
      user_id: "user-1",
    },
  ],
  total_horas: 1.5,
  horas_a_faturar: 1.5,
};

describe("LinhaDoTempoProcessual", () => {
  beforeEach(() => {
    get.mockReset();
    toastError.mockReset();
  });

  it("consolida movimentos processuais e atividades do timesheet", async () => {
    get.mockImplementation((url: string) => {
      if (url.includes("/visual-law/")) return Promise.resolve({ data: timeline });
      if (url.includes("/timesheet/")) return Promise.resolve({ data: timesheet });
      return Promise.reject(new Error("endpoint inesperado"));
    });

    render(<LinhaDoTempoProcessual caseId="case-1" />);

    expect(await screen.findByText("Eventos do caso")).toBeTruthy();
    expect(screen.getByText(/Revisão da contestação/)).toBeTruthy();
    expect(screen.getByText(/1.5h registradas/)).toBeTruthy();
    expect(screen.getByText(/1.5h a faturar/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Atividades" })).toBeTruthy();
  });

  it("mantém a timeline jurídica disponível quando o timesheet falha", async () => {
    get.mockImplementation((url: string) => {
      if (url.includes("/visual-law/")) return Promise.resolve({ data: timeline });
      if (url.includes("/timesheet/")) return Promise.reject(new Error("offline"));
      return Promise.reject(new Error("endpoint inesperado"));
    });

    render(<LinhaDoTempoProcessual caseId="case-1" />);

    expect(await screen.findByText("Contestação juntada")).toBeTruthy();
    expect(
      screen.getByText(/As atividades de horas não puderam ser incorporadas/),
    ).toBeTruthy();
    await waitFor(() => expect(toastError).not.toHaveBeenCalled());
  });
});
