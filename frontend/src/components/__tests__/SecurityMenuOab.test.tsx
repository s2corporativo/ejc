// ── SecurityMenu — modal "Minha OAB (intimações DJEN)" ───────────────────────
// O modal abria SEMPRE vazio, mesmo com OAB já gravada, e o botão "Salvar"
// enviava string vazia: quem abria só para conferir apagava a própria OAB e
// recebia o toast "OAB salva". A captura das 06h30 parava em silêncio — num
// sistema de prazos, isso é intimação perdida. Estes testes travam as três
// garantias: o modal carrega o valor salvo, não grava par pela metade, e
// desligar o monitoramento é um ato explícito.
import { describe, it, expect, beforeEach, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const apiPatch = vi.fn();
vi.mock("../../lib/api", () => ({
  __esModule: true,
  default: {
    patch: (...args: unknown[]) => apiPatch(...args),
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
  logout: vi.fn(),
}));

const updateUser = vi.fn();
vi.mock("../../stores/auth", () => ({
  useAuth: () => ({ updateUser }),
}));

const toastError = vi.fn();
const toastSuccess = vi.fn();
vi.mock("../Toast", () => ({
  toast: {
    error: (...a: unknown[]) => toastError(...a),
    success: (...a: unknown[]) => toastSuccess(...a),
    info: vi.fn(),
  },
}));

vi.mock("react-router", () => ({ useNavigate: () => vi.fn() }));

import SecurityMenu from "../SecurityMenu";

const USUARIO_COM_OAB = {
  id: "u-1",
  full_name: "Advogada Teste",
  role: "advogado",
  djen_oab_numero: "252599",
  djen_oab_uf: "MG",
};

function abrirModalOab() {
  fireEvent.click(screen.getByRole("button", { name: /Advogada Teste/i }));
  fireEvent.click(screen.getByText(/Minha OAB/i));
}

describe("SecurityMenu — OAB do DJEN", () => {
  beforeEach(() => {
    apiPatch.mockReset().mockResolvedValue({ data: {} });
    updateUser.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
  });

  it("abre o modal já preenchido com a OAB salva", () => {
    render(<SecurityMenu user={USUARIO_COM_OAB} />);
    abrirModalOab();
    expect(
      (screen.getByPlaceholderText(/Número/i) as HTMLInputElement).value,
    ).toBe("252599");
    expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe(
      "MG",
    );
  });

  it("oferece as 27 unidades federativas", () => {
    render(<SecurityMenu user={USUARIO_COM_OAB} />);
    abrirModalOab();
    expect(
      (screen.getByRole("combobox") as HTMLSelectElement).options.length,
    ).toBe(27);
  });

  it("não grava OAB vazia — não apaga o monitoramento por engano", async () => {
    render(<SecurityMenu user={USUARIO_COM_OAB} />);
    abrirModalOab();
    fireEvent.change(screen.getByPlaceholderText(/Número/i), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Salvar$/ }));
    await waitFor(() => expect(toastError).toHaveBeenCalled());
    expect(apiPatch).not.toHaveBeenCalled();
  });

  it("salva o par número+UF e atualiza o estado local", async () => {
    render(
      <SecurityMenu user={{ ...USUARIO_COM_OAB, djen_oab_numero: null }} />,
    );
    abrirModalOab();
    fireEvent.change(screen.getByPlaceholderText(/Número/i), {
      target: { value: "251174" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Salvar$/ }));
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    expect(apiPatch).toHaveBeenCalledWith("/users/u-1", {
      djen_oab_numero: "251174",
      djen_oab_uf: "MG",
    });
    expect(updateUser).toHaveBeenCalledWith({
      djen_oab_numero: "251174",
      djen_oab_uf: "MG",
    });
  });

  it("desligar o monitoramento é um ato explícito e separado", async () => {
    render(<SecurityMenu user={USUARIO_COM_OAB} />);
    abrirModalOab();
    fireEvent.click(screen.getByText(/Parar de monitorar/i));
    await waitFor(() => expect(apiPatch).toHaveBeenCalled());
    expect(apiPatch).toHaveBeenCalledWith("/users/u-1", {
      djen_oab_numero: "",
      djen_oab_uf: "",
    });
    expect(updateUser).toHaveBeenCalledWith({
      djen_oab_numero: null,
      djen_oab_uf: null,
    });
  });

  it("sem OAB salva, não oferece o botão de parar de monitorar", () => {
    render(
      <SecurityMenu
        user={{ ...USUARIO_COM_OAB, djen_oab_numero: null, djen_oab_uf: null }}
      />,
    );
    abrirModalOab();
    expect(screen.queryByText(/Parar de monitorar/i)).toBeNull();
  });
});
