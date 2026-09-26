// @vitest-environment jsdom
import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import api from "../../lib/api";
import { useAuth } from "../../stores/auth";
import RamoBase from "./RamoBase";

vi.mock("../../lib/api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock("../../stores/auth", () => ({
  useAuth: vi.fn(),
}));

const getMock = vi.mocked(api.get);
const useAuthMock = vi.mocked(useAuth);

beforeEach(() => {
  vi.clearAllMocks();
  useAuthMock.mockImplementation((seletor: any) =>
    seletor({ user: { role: "admin" } }),
  );
  getMock.mockResolvedValue({ data: { data: [], total: 0 } } as any);
});

describe("RamoBase — fallback estável", () => {
  it("carrega casos uma única vez ao montar uma área genérica", async () => {
    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/areas-de-atuacao/societario"]}>
          <Routes>
            <Route path="/areas-de-atuacao/:slug" element={<RamoBase />} />
          </Routes>
        </MemoryRouter>,
      );
    });

    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(1));
    expect(getMock).toHaveBeenCalledWith("/cases/", {
      params: { area: "societario", page_size: 100 },
    });
  });
});


  it("preserva case_id e abre a aba solicitada sem exibir outros casos", async () => {
    getMock.mockImplementation(async (url: string) => {
      if (url === "/cases/case-ctx") {
        return {
          data: {
            id: "case-ctx",
            titulo: "Caso contextual",
            status: "aberto",
            area: "societario",
            prioridade: "media",
            created_at: "2026-09-26T12:00:00Z",
          },
        } as any;
      }
      if (url === "/cases/case-ctx/areas") {
        return {
          data: { areas: [{ area: "societario", principal: true }] },
        } as any;
      }
      return { data: { data: [], total: 0 } } as any;
    });

    await act(async () => {
      render(
        <MemoryRouter
          initialEntries={[
            "/areas-de-atuacao/societario?case_id=case-ctx&tab=casos",
          ]}
        >
          <Routes>
            <Route path="/areas-de-atuacao/:slug" element={<RamoBase />} />
          </Routes>
        </MemoryRouter>,
      );
    });

    await waitFor(() => expect(screen.getByText("Caso contextual")).toBeTruthy());
    expect(screen.queryByText("Caso fora do contexto")).toBeNull();
    expect(getMock).not.toHaveBeenCalledWith("/cases/", expect.anything());
    expect(
      screen.getByRole("link", { name: "Voltar ao caso" }).getAttribute("href"),
    ).toBe("/casos/case-ctx");
  });
