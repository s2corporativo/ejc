import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("../../../lib/api", () => ({
  default: {
    get: mocks.get,
  },
}));

vi.mock("../../../components/Toast", () => ({
  toast: {
    error: mocks.toastError,
  },
}));

vi.mock("../../../components/ProvasCaso", () => ({
  default: ({ caseId }: { caseId: string }) => (
    <div>Mapa probatório do caso {caseId}</div>
  ),
}));

import TabArquivos from "../TabArquivos";

function renderPainel(
  secaoAtiva: "documentos" | "provas" | "contratos" | "procuracoes",
  onSecaoChange = vi.fn(),
  clientId: string | null = "cliente 1",
) {
  return render(
    <MemoryRouter>
      <TabArquivos
        caseId="case-1"
        clientId={clientId}
        secaoAtiva={secaoAtiva}
        onSecaoChange={onSecaoChange}
      />
    </MemoryRouter>,
  );
}

describe("TabArquivos", () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.toastError.mockReset();
  });

  it("reúne os quatro tipos e carrega documentos do caso", async () => {
    mocks.get.mockResolvedValue({
      data: [{ id: "doc-1", titulo: "Petição inicial", tipo: "Peça" }],
    });

    renderPainel("documentos");

    expect(screen.getAllByRole("tab")).toHaveLength(4);
    expect(
      screen.getByRole("tab", { name: "Documentos" }).getAttribute(
        "aria-selected",
      ),
    ).toBe("true");
    expect(
      screen.getByRole("link", { name: "Anexar documento" }).getAttribute("href"),
    ).toBe("/documentos?caso=case-1");

    expect(await screen.findByText("Petição inicial")).toBeTruthy();
    expect(mocks.get).toHaveBeenCalledWith("/documents/?case_id=case-1");
  });

  it("entrega a troca de filtro ao controlador da URL", () => {
    mocks.get.mockResolvedValue({ data: [] });
    const onSecaoChange = vi.fn();

    renderPainel("documentos", onSecaoChange);
    fireEvent.click(screen.getByRole("tab", { name: "Contratos" }));

    expect(onSecaoChange).toHaveBeenCalledWith("contratos");
  });

  it("preserva o mapa probatório existente na seção Provas", () => {
    renderPainel("provas");

    expect(screen.getByText("Mapa probatório do caso case-1")).toBeTruthy();
    expect(mocks.get).not.toHaveBeenCalled();
  });

  it("codifica o identificador do cliente ao carregar procurações", async () => {
    mocks.get.mockResolvedValue({ data: [] });

    renderPainel("procuracoes");

    await screen.findByText("Nenhuma procuração do cliente");
    expect(mocks.get).toHaveBeenCalledWith(
      "/procuracoes/?client_id=cliente%201",
    );
  });

  it("não consulta procurações quando o cliente do caso está ausente", () => {
    renderPainel("procuracoes", vi.fn(), null);

    expect(
      screen.getByText(/cliente do caso não foi identificado/i),
    ).toBeTruthy();
    expect(mocks.get).not.toHaveBeenCalled();
  });
});
