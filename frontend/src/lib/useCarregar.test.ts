import { describe, expect, it } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import {
  MENSAGEM_SEM_PERMISSAO,
  mensagemDaFalha,
  useCarregar,
} from "./useCarregar";

function erroHttp(status: number, detail?: unknown) {
  return Object.assign(new Error(`HTTP ${status}`), {
    response: { status, data: { detail } },
  });
}

describe("useCarregar", () => {
  it("começa em carregando e termina em ok com dados", async () => {
    const { result } = renderHook(() =>
      useCarregar(() => Promise.resolve([{ id: 1 }]), []),
    );
    expect(result.current.estado).toBe("carregando");
    await waitFor(() => expect(result.current.estado).toBe("ok"));
    expect(result.current.dados).toEqual([{ id: 1 }]);
    expect(result.current.erro).toBeNull();
  });

  it("array vazio ou null viram estado vazio", async () => {
    const lista = renderHook(() => useCarregar(() => Promise.resolve([]), []));
    await waitFor(() => expect(lista.result.current.estado).toBe("vazio"));
    const nulo = renderHook(() => useCarregar(() => Promise.resolve(null), []));
    await waitFor(() => expect(nulo.result.current.estado).toBe("vazio"));
  });

  it("aceita critério de vazio customizado", async () => {
    const { result } = renderHook(() =>
      useCarregar(() => Promise.resolve({ total: 0 }), [], {
        vazio: (d) => d.total === 0,
      }),
    );
    await waitFor(() => expect(result.current.estado).toBe("vazio"));
  });

  it("falha vira estado falhou com mensagem leiga e status", async () => {
    const { result } = renderHook(() =>
      useCarregar(
        () => Promise.reject(erroHttp(500, "Traceback: KeyError provider")),
        [],
        { fallbackErro: "Falha ao carregar partes" },
      ),
    );
    await waitFor(() => expect(result.current.estado).toBe("falhou"));
    // detail técnico nunca chega à tela: cai no fallback
    expect(result.current.erro).toBe("Falha ao carregar partes");
    expect(result.current.status).toBe(500);
  });

  it("422 com array de validação não vaza objeto", async () => {
    const { result } = renderHook(() =>
      useCarregar(
        () =>
          Promise.reject(
            erroHttp(422, [
              { loc: ["body", "area"], msg: "campo obrigatório" },
            ]),
          ),
        [],
      ),
    );
    await waitFor(() => expect(result.current.estado).toBe("falhou"));
    expect(typeof result.current.erro).toBe("string");
    expect(result.current.erro).toContain("area");
  });

  it("recarregar() refaz a chamada e sai do estado falhou", async () => {
    let tentativa = 0;
    const carregador = () => {
      tentativa += 1;
      return tentativa === 1
        ? Promise.reject(erroHttp(503))
        : Promise.resolve(["ok"]);
    };
    const { result } = renderHook(() => useCarregar(carregador, []));
    await waitFor(() => expect(result.current.estado).toBe("falhou"));
    act(() => result.current.recarregar());
    await waitFor(() => expect(result.current.estado).toBe("ok"));
    expect(tentativa).toBe(2);
  });

  it("resposta atrasada de dependência antiga não sobrescreve a nova", async () => {
    const pendentes: Record<string, (v: string[]) => void> = {};
    const carregador = (id: string) =>
      new Promise<string[]>((resolve) => {
        pendentes[id] = resolve;
      });
    const { result, rerender } = renderHook(
      ({ id }) => useCarregar(() => carregador(id), [id]),
      { initialProps: { id: "a" } },
    );
    rerender({ id: "b" });
    await waitFor(() => expect(pendentes.b).toBeDefined());
    act(() => pendentes.b(["dados-b"]));
    await waitFor(() => expect(result.current.estado).toBe("ok"));
    act(() => pendentes.a(["dados-a"]));
    expect(result.current.dados).toEqual(["dados-b"]);
  });

  it("habilitado=false não dispara a carga", () => {
    let chamadas = 0;
    const { result } = renderHook(() =>
      useCarregar(
        () => {
          chamadas += 1;
          return Promise.resolve([]);
        },
        [],
        { habilitado: false },
      ),
    );
    expect(chamadas).toBe(0);
    expect(result.current.estado).toBe("vazio");
  });
});

describe("mensagemDaFalha", () => {
  it("403 vira mensagem de permissão", () => {
    expect(mensagemDaFalha({ erro: "x", status: 403 })).toBe(
      MENSAGEM_SEM_PERMISSAO,
    );
  });
  it("demais status usam a mensagem do hook", () => {
    expect(mensagemDaFalha({ erro: "Falhou", status: 500 })).toBe("Falhou");
  });
});
