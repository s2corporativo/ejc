// @vitest-environment jsdom
// Onda 3 (§10: Caso como workspace central) — a aba "Data Room" do caso usa a
// MESMA superfície canônica do módulo (sem segundo CRUD): com `caseId`, o
// painel filtra as salas do caso e a criação já nasce vinculada (case_id).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("../components/Toast", () => ({
  toast: { info: vi.fn(), error: vi.fn(), success: vi.fn() },
}));

import api from "../lib/api";
import { DataRoomPanel } from "./DataRoom";

vi.mock("../lib/api", () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

const SALAS = [
  { id: "sala-caso", nome: "Sala do caso", case_id: "c1", created_at: "2026-09-01" },
  { id: "sala-outro", nome: "Sala de outro caso", case_id: "c2", created_at: "2026-09-02" },
  { id: "sala-global", nome: "Sala sem caso", created_at: "2026-09-03" },
];

beforeEach(() => {
  vi.mocked(api.get).mockResolvedValue({ data: SALAS });
  vi.mocked(api.post).mockResolvedValue({ data: {} });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("DataRoomPanel — contexto de caso (Onda 3)", () => {
  it("sem caseId (página global): lista todas as salas acessíveis", async () => {
    render(<DataRoomPanel />);
    await waitFor(() => expect(screen.getByText("Sala do caso")).toBeTruthy());
    expect(screen.getByText("Sala de outro caso")).toBeTruthy();
    expect(screen.getByText("Sala sem caso")).toBeTruthy();
    expect(screen.getByText("Data Room")).toBeTruthy();
  });

  it("com caseId: lista só as salas do caso e rotula 'Data Room do caso'", async () => {
    render(<DataRoomPanel caseId="c1" />);
    await waitFor(() => expect(screen.getByText("Sala do caso")).toBeTruthy());
    expect(screen.queryByText("Sala de outro caso")).toBeNull();
    expect(screen.queryByText("Sala sem caso")).toBeNull();
    expect(screen.getByText("Data Room do caso")).toBeTruthy();
  });

  it("com caseId: estado vazio honesto quando o caso não tem sala", async () => {
    render(<DataRoomPanel caseId="c-inexistente" />);
    await waitFor(() =>
      expect(screen.getByText("Nenhuma sala vinculada a este caso")).toBeTruthy(),
    );
  });

  it("com caseId: nova sala nasce vinculada ao caso (POST com case_id)", async () => {
    render(<DataRoomPanel caseId="c1" />);
    await waitFor(() => expect(screen.getByText("+ Nova sala")).toBeTruthy());

    fireEvent.click(screen.getByText("+ Nova sala"));
    fireEvent.change(screen.getByLabelText("Nome *"), {
      target: { value: "Sala nova do caso" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Criar" }));

    await waitFor(() =>
      expect(vi.mocked(api.post)).toHaveBeenCalled(),
    );
    const [rota, corpo] = vi.mocked(api.post).mock.calls[0];
    expect(rota).toBe("/data-rooms");
    expect((corpo as any).case_id).toBe("c1");
    expect((corpo as any).nome).toBe("Sala nova do caso");
  });

  it("sem caseId: POST global permanece sem case_id (contrato atual)", async () => {
    render(<DataRoomPanel />);
    await waitFor(() => expect(screen.getByText("+ Nova sala")).toBeTruthy());

    fireEvent.click(screen.getByText("+ Nova sala"));
    fireEvent.change(screen.getByLabelText("Nome *"), {
      target: { value: "Sala avulsa" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Criar" }));

    await waitFor(() => expect(vi.mocked(api.post)).toHaveBeenCalled());
    const [, corpo] = vi.mocked(api.post).mock.calls[0];
    expect((corpo as any).case_id).toBeUndefined();
  });
});
