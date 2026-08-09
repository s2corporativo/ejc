// @vitest-environment jsdom
import { act, render, waitFor } from "@testing-library/react";
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
