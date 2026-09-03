import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  ERRO_JUSTIFICATIVA_OBRIGATORIA,
  bloqueioDeCitacoes,
  useOverrideCitacoes,
  type CamposOverride,
} from "./OverrideCitacoesDialog";

function erro409() {
  return Object.assign(new Error("409"), {
    response: {
      status: 409,
      data: {
        detail: {
          erro: "citacoes_nao_verificadas",
          mensagem: "Output de IA contém citações bloqueantes.",
          politica: "bloquear",
          score: 0.4,
          motivos: ["Súmula 999 do STJ não localizada"],
          bloqueantes: [{ trecho: "Súmula 999/STJ", motivo: "inexistente" }],
        },
      },
    },
  });
}

describe("bloqueioDeCitacoes", () => {
  it("reconhece só o 409 do gate", () => {
    expect(bloqueioDeCitacoes(erro409())?.motivos).toEqual([
      "Súmula 999 do STJ não localizada",
    ]);
    expect(
      bloqueioDeCitacoes(
        Object.assign(new Error(), {
          response: { status: 409, data: { detail: "versão anterior" } },
        }),
      ),
    ).toBeNull();
    expect(bloqueioDeCitacoes(new Error("rede"))).toBeNull();
  });
});

function Harness({
  enviar,
  onOk,
}: {
  enviar: (extra: CamposOverride) => Promise<unknown>;
  onOk: () => void;
}) {
  const override = useOverrideCitacoes();
  return (
    <div>
      <button
        onClick={() =>
          void override.executar(enviar).then((ok) => ok && onOk())
        }
      >
        marcar
      </button>
      {override.dialogo(onOk)}
    </div>
  );
}

describe("useOverrideCitacoes (E5)", () => {
  it("409 abre diálogo; justificativa obrigatória; reenvio leva override", async () => {
    const chamadas: CamposOverride[] = [];
    const enviar = vi.fn((extra: CamposOverride) => {
      chamadas.push(extra);
      return chamadas.length === 1
        ? Promise.reject(erro409())
        : Promise.resolve({});
    });
    const onOk = vi.fn();
    render(<Harness enviar={enviar} onOk={onOk} />);
    fireEvent.click(screen.getByText("marcar"));
    expect(await screen.findByText("Citações não confirmadas")).toBeTruthy();
    expect(screen.getByText(/Súmula 999 do STJ não localizada/)).toBeTruthy();
    expect(onOk).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", { name: /Aprovar com justificativa/ }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      ERRO_JUSTIFICATIVA_OBRIGATORIA,
    );
    expect(enviar).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByLabelText("Justificativa do override"), {
      target: { value: "Conferi no site do STJ em 01/09." },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Aprovar com justificativa/ }),
    );
    await waitFor(() => expect(onOk).toHaveBeenCalledTimes(1));
    expect(chamadas[1]).toEqual({
      override_citacoes: true,
      justificativa_override: "Conferi no site do STJ em 01/09.",
    });
    expect(screen.queryByText("Citações não confirmadas")).toBeNull();
  });

  it("erro que não é do gate é relançado ao chamador", async () => {
    const enviar = vi.fn(() =>
      Promise.reject(
        Object.assign(new Error(), {
          response: { status: 403, data: { detail: "sem permissão" } },
        }),
      ),
    );
    let capturado: unknown = null;
    function H() {
      const override = useOverrideCitacoes();
      return (
        <button
          onClick={() =>
            void override.executar(enviar).catch((e) => {
              capturado = e;
            })
          }
        >
          marcar
        </button>
      );
    }
    render(<H />);
    fireEvent.click(screen.getByText("marcar"));
    await waitFor(() => expect(capturado).not.toBeNull());
    expect(screen.queryByText("Citações não confirmadas")).toBeNull();
  });
});
