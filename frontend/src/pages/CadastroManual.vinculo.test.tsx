// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import api from "../lib/api";
import { useCadastroManualStore } from "../stores/cadastroManual";
import CadastroManual from "./CadastroManual";

vi.mock("../stores/auth", () => ({
  useAuth: (selector: (state: unknown) => unknown) =>
    selector({ user: { id: "usuario-b", role: "secretaria" } }),
}));

vi.mock("../components/Toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

function campoTitulo() {
  const label = screen.getByText("Título do caso *");
  const campo = label.parentElement?.querySelector("input");
  if (!campo) throw new Error("Campo de título não encontrado");
  return campo as HTMLInputElement;
}

function renderCadastro() {
  return render(
    <MemoryRouter initialEntries={["/entrada?modo=manual&aba=caso"]}>
      <CadastroManual />
    </MemoryRouter>,
  );
}

describe("CadastroManual — rascunho persistido e troca de usuário", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.spyOn(api, "get").mockResolvedValue({ data: { data: [] } });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("descarta o rascunho de outro usuário e não o regrava sob o usuário logado", async () => {
    useCadastroManualStore.setState({
      usuarioId: "usuario-a",
      rascunhoCliente: { nome: "Cliente sigiloso de A" },
      rascunhoCaso: { titulo: "Caso sigiloso de A" },
      fila: [],
      clientesCache: [],
      sincronizando: false,
    });

    renderCadastro();

    await waitFor(() => expect(campoTitulo().value).toBe(""));
    const estado = useCadastroManualStore.getState();
    expect(estado.usuarioId).toBe("usuario-b");
    expect(JSON.stringify(estado.rascunhoCaso)).not.toContain(
      "Caso sigiloso de A",
    );
    expect(JSON.stringify(estado.rascunhoCliente)).not.toContain(
      "Cliente sigiloso de A",
    );
  });

  it("preserva o rascunho do próprio usuário", async () => {
    useCadastroManualStore.setState({
      usuarioId: "usuario-b",
      rascunhoCliente: {},
      rascunhoCaso: { titulo: "Meu caso em rascunho" },
      fila: [],
      clientesCache: [],
      sincronizando: false,
    });

    renderCadastro();

    await waitFor(() =>
      expect(campoTitulo().value).toBe("Meu caso em rascunho"),
    );
    expect(
      (useCadastroManualStore.getState().rascunhoCaso as { titulo?: string })
        .titulo,
    ).toBe("Meu caso em rascunho");
  });
});
