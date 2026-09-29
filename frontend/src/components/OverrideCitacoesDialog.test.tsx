import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  ERRO_JUSTIFICATIVA_OBRIGATORIA,
  OverrideCitacoesDialog,
  bloqueioDeCitacoes,
  useOverrideCitacoes,
  type BloqueioCitacoes,
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

    // O diálogo tem um efeito de montagem que limpa `justificativa` e o erro
    // local sempre que `bloqueio` muda (para não vazar texto de um documento
    // para o próximo). `findByText` do RTL não passa pelo `act`, então sob
    // carga da suíte completa ele pode resolver ANTES desse efeito passivo
    // rodar. O clique abaixo entra num `act` que processa o `setErroLocal`
    // do handler e, na sequência, o reset pendente — e o alerta nunca chega
    // ao DOM ("Unable to find role=alert", intermitente). Forçar o flush aqui
    // garante que o clique interage com o diálogo já estabilizado, que é o
    // único estado que um usuário consegue alcançar.
    await act(async () => {});

    fireEvent.click(
      screen.getByRole("button", { name: /Aprovar com justificativa/ }),
    );
    // Espera explícita: o `getByRole` síncrono falhava de forma intermitente
    // sob a carga da suíte completa ("Unable to find an accessible element with
    // the role 'alert'"), passando isolado e no reteste. `findByRole` tolera o
    // tick de render sem afrouxar a asserção — o alerta continua obrigatório.
    const alerta = await screen.findByRole("alert");
    expect(alerta.textContent).toContain(ERRO_JUSTIFICATIVA_OBRIGATORIA);
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

// ── Revisão automatizada do PR (03/09/2026) ─────────────────────────────────
// O diálogo não desmonta entre um bloqueio e outro: sem limpar o estado, a
// justificativa escrita para UMA citação bloqueada reaparecia no override do
// PRÓXIMO caso e seria gravada em auditoria como justificativa daquele.
describe("limpeza de estado entre bloqueios", () => {
  function Palco({ bloqueio }: { bloqueio: BloqueioCitacoes | null }) {
    return (
      <OverrideCitacoesDialog
        bloqueio={bloqueio}
        onCancelar={() => {}}
        onConfirmar={() => {}}
      />
    );
  }

  const bloqueio = (mensagem: string): BloqueioCitacoes => ({
    mensagem,
    motivos: [],
    bloqueantes: [],
  });

  it("zera a justificativa quando o bloqueio muda", () => {
    const { rerender } = render(<Palco bloqueio={bloqueio("primeiro")} />);
    const campo = () =>
      screen.getByLabelText("Justificativa do override") as HTMLTextAreaElement;

    fireEvent.change(campo(), {
      target: { value: "conferido no TJMG em 01/09" },
    });
    expect(campo().value).toBe("conferido no TJMG em 01/09");

    rerender(<Palco bloqueio={bloqueio("segundo")} />);
    expect(campo().value).toBe("");
  });

  it("zera o erro de validação ao fechar e reabrir", () => {
    const { rerender } = render(<Palco bloqueio={bloqueio("primeiro")} />);
    fireEvent.click(
      screen.getByRole("button", { name: /Aprovar com justificativa/ }),
    );
    expect(screen.getByRole("alert").textContent).toContain(
      ERRO_JUSTIFICATIVA_OBRIGATORIA,
    );

    rerender(<Palco bloqueio={null} />);
    rerender(<Palco bloqueio={bloqueio("segundo")} />);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
