// @vitest-environment jsdom
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import api from "../../lib/api";
import type { Case } from "../../types";
import FichaEspecializada from "./FichaEspecializada";
import type { RamoConfig } from "./ramosConfig";

vi.mock("../../lib/api", () => ({
  default: {
    post: vi.fn(),
  },
}));

vi.mock("../../components/UI", () => ({
  Modal: ({ open, children }: { open: boolean; children: React.ReactNode }) =>
    open ? <div data-testid="modal">{children}</div> : null,
}));

const postMock = vi.mocked(api.post);

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

function criarConfiguracao(
  slug: string,
  titulo: string,
  campo: string,
): RamoConfig {
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
    const cfgA = criarConfiguracao("area-a", "Área A", "campo_a");
    const cfgB = criarConfiguracao("area-b", "Área B", "campo_b");
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

  it("ignora a conclusão de gravação iniciada no workspace anterior", async () => {
    const cfgA = criarConfiguracao("area-a", "Área A", "campo_a");
    const cfgB = criarConfiguracao("area-b", "Área B", "campo_b");
    const onSavedA = vi.fn();
    const onSavedB = vi.fn();
    let concluirGravacaoA: ((value: unknown) => void) | undefined;

    postMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          concluirGravacaoA = resolve;
        }) as any,
    );

    const { rerender } = render(
      <FichaEspecializada cfg={cfgA} casos={[casoA]} onSaved={onSavedA} />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /adicionar ficha especializada/i }),
    );
    const [seletorCasoA] = screen.getAllByRole("combobox");
    fireEvent.change(seletorCasoA, { target: { value: "caso-a" } });
    fireEvent.click(
      screen.getByRole("button", { name: "Salvar ficha especializada" }),
    );
    expect(postMock).toHaveBeenCalledTimes(1);

    rerender(
      <FichaEspecializada cfg={cfgB} casos={[casoB]} onSaved={onSavedB} />,
    );
    await waitFor(() => expect(screen.queryByTestId("modal")).toBeNull());

    fireEvent.click(
      screen.getByRole("button", { name: /adicionar ficha especializada/i }),
    );
    const [seletorCasoB] = screen.getAllByRole("combobox");
    fireEvent.change(seletorCasoB, { target: { value: "caso-b" } });
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "rascunho da área B" },
    });

    await act(async () => {
      concluirGravacaoA?.({ data: {} });
      await Promise.resolve();
    });

    expect(screen.getByTestId("modal")).toBeTruthy();
    expect((seletorCasoB as HTMLSelectElement).value).toBe("caso-b");
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe(
      "rascunho da área B",
    );
    expect(onSavedA).not.toHaveBeenCalled();
    expect(onSavedB).not.toHaveBeenCalled();
  });
});
