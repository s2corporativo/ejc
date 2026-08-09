// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Case } from "../../types";
import FichaEspecializada from "./FichaEspecializada";
import type { RamoConfig } from "./ramosConfig";

vi.mock("../../components/UI", () => ({
  Modal: ({ open, children }: { open: boolean; children: React.ReactNode }) =>
    open ? <div data-testid="modal">{children}</div> : null,
}));

const casoA = {
  id: "caso-a",
  titulo: "Caso A",
  numero_interno: "A-001",
} as Case;

const casoB = {
  id: "caso-b",
  titulo: "Caso B",
  numero_interno: "B-001",
} as Case;

function config(slug: string, titulo: string, campo: string): RamoConfig {
  return {
    slug,
    endpoint: `/api/${slug}`,
    areaCaso: slug,
    titulo,
    subtitulo: titulo,
    icone: "Folder",
    cor: "slate",
    campoTitulo: "tipo",
    campoStatus: "status",
    campos: [{ nome: campo, label: `Campo ${slug}`, tipo: "text" }],
    ferramentas: [],
  };
}

describe("FichaEspecializada — troca de workspace", () => {
  it("descarta case_id e campos da área anterior quando cfg.slug muda", async () => {
    const cfgA = config("area-a", "Área A", "campo_a");
    const cfgB = config("area-b", "Área B", "campo_b");
    const { rerender } = render(
      <FichaEspecializada cfg={cfgA} casos={[casoA]} />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /adicionar ficha especializada/i }),
    );
    const [seletorCaso] = screen.getAllByRole("combobox");
    fireEvent.change(seletorCaso, { target: { value: "caso-a" } });
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "valor antigo" },
    });
    expect((seletorCaso as HTMLSelectElement).value).toBe("caso-a");
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe(
      "valor antigo",
    );

    rerender(<FichaEspecializada cfg={cfgB} casos={[casoB]} />);

    await waitFor(() => expect(screen.queryByTestId("modal")).toBeNull());
    fireEvent.click(
      screen.getByRole("button", { name: /adicionar ficha especializada/i }),
    );

    const [novoSeletorCaso] = screen.getAllByRole("combobox");
    expect((novoSeletorCaso as HTMLSelectElement).value).toBe("");
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("");
  });
});
