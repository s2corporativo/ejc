import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  CADASTRO_MANUAL_KEY,
  MSG_AMBIGUO,
  classificarErro,
  useCadastroManualStore,
  type PostFn,
} from "./cadastroManual";

const store = useCadastroManualStore;

function erroHttp(status: number, detail?: unknown) {
  return { response: { status, data: detail === undefined ? {} : { detail } } };
}

describe("cadastroManual — fila offline", () => {
  beforeEach(() => {
    localStorage.removeItem(CADASTRO_MANUAL_KEY);
    store.setState({
      rascunhoCliente: {},
      rascunhoCaso: {},
      fila: [],
      clientesCache: [],
      usuarioId: "user-1",
      sincronizando: false,
    });
  });

  it("(a) enfileira cliente com dono e sincroniza 2xx removendo-o", async () => {
    store.getState().enfileirar("cliente", { tipo: "PF", nome: "Maria" });
    expect(store.getState().fila).toHaveLength(1);
    expect(store.getState().fila[0].usuarioId).toBe("user-1");

    const post: PostFn = vi.fn(async () => ({ id: "client-real" }));
    const resultado = await store.getState().sincronizar(post);

    expect(post).toHaveBeenCalledWith("/clients/", {
      tipo: "PF",
      nome: "Maria",
    });
    expect(resultado.enviados).toHaveLength(1);
    expect(store.getState().fila).toHaveLength(0);
  });

  it("(b) resolve cliente local antes de enviar caso dependente", async () => {
    const clienteLocal = store
      .getState()
      .enfileirar("cliente", { tipo: "PF", nome: "Maria" });
    store
      .getState()
      .enfileirar(
        "caso",
        { titulo: "Caso Maria", client_id: clienteLocal },
        clienteLocal,
      );

    const post: PostFn = vi.fn(async (path) =>
      path === "/clients/" ? { id: "client-real" } : { id: "case-real" },
    );
    await store.getState().sincronizar(post);

    expect(post).toHaveBeenNthCalledWith(1, "/clients/", {
      tipo: "PF",
      nome: "Maria",
    });
    expect(post).toHaveBeenNthCalledWith(2, "/cases/", {
      titulo: "Caso Maria",
      client_id: "client-real",
    });
    expect(store.getState().fila).toHaveLength(0);
  });

  it("(b2) resposta 2xx sem id deixa caso dependente pendente, sem enviá-lo", async () => {
    const clienteLocal = store
      .getState()
      .enfileirar("cliente", { tipo: "PF", nome: "Maria" });
    store
      .getState()
      .enfileirar(
        "caso",
        { titulo: "Caso Maria", client_id: clienteLocal },
        clienteLocal,
      );

    const post: PostFn = vi.fn(async () => ({}));
    const resultado = await store.getState().sincronizar(post);

    expect(post).toHaveBeenCalledTimes(1);
    expect(resultado.enviados).toHaveLength(0);
    expect(resultado.comErro).toBe(1);
    expect(resultado.pendentes).toBe(1);
    expect(store.getState().fila).toHaveLength(2);
    expect(store.getState().fila[0].status).toBe("erro");
    expect(store.getState().fila[1].status).toBe("pendente");
  });

  it("(c) 4xx vira status 'erro' com a mensagem do backend, não é descartado nem re-tentado", async () => {
    store.getState().enfileirar("cliente", { tipo: "PF", nome: "Maria" });
    const post: PostFn = vi.fn(async () => {
      throw erroHttp(422, "CPF inválido (dígito verificador)");
    });

    await store.getState().sincronizar(post);
    let fila = store.getState().fila;
    expect(fila).toHaveLength(1);
    expect(fila[0].status).toBe("erro");
    expect(fila[0].erro).toBe("CPF inválido (dígito verificador)");

    // Segundo sync NÃO re-tenta item em erro.
    await store.getState().sincronizar(post);
    fila = store.getState().fila;
    expect(post).toHaveBeenCalledTimes(1);
    expect(fila[0].status).toBe("erro");
  });

  it("(c2) 422 do Pydantic (detail em lista) identifica o campo e a mensagem", () => {
    const c = classificarErro(
      erroHttp(422, [{ loc: ["body", "area"], msg: "Área inválida" }]),
    );
    expect(c).toEqual({ acao: "erro", mensagem: "area: Área inválida" });
  });

  it("(c3) timeout/5xx (ambíguo) vira 'erro' pedindo verificação manual, sem reenvio", async () => {
    expect(classificarErro({ code: "ECONNABORTED" })).toEqual({
      acao: "erro",
      mensagem: MSG_AMBIGUO,
    });
    expect(classificarErro(erroHttp(500))).toEqual({
      acao: "erro",
      mensagem: MSG_AMBIGUO,
    });
  });

  it("(d) erro de rede (sem resposta) mantém o item 'pendente' para o próximo gatilho", async () => {
    store.getState().enfileirar("cliente", { tipo: "PF", nome: "Maria" });
    const post: PostFn = vi.fn(async () => {
      throw new Error("offline");
    });

    const resultado = await store.getState().sincronizar(post);
    expect(resultado.pendentes).toBe(1);
    expect(store.getState().fila[0].status).toBe("pendente");
  });

  it("(e) não sincroniza item persistido de outro usuário", async () => {
    store.setState({
      fila: [
        {
          id: "foreign",
          tipo: "cliente",
          payload: { tipo: "PF", nome: "Outro" },
          criado_em: new Date().toISOString(),
          status: "pendente",
          usuarioId: "user-2",
        },
      ],
    });
    const post: PostFn = vi.fn(async () => ({ id: "x" }));

    await store.getState().sincronizar(post);
    expect(post).not.toHaveBeenCalled();
    expect(store.getState().fila).toHaveLength(1);
  });

  it("(f) vincularUsuario descarta PII persistida de outra conta", () => {
    store.setState({
      usuarioId: "user-2",
      fila: [
        {
          id: "foreign",
          tipo: "cliente",
          payload: { tipo: "PF", nome: "Outra pessoa" },
          criado_em: new Date().toISOString(),
          status: "pendente",
          usuarioId: "user-2",
        },
      ],
      rascunhoCliente: { nome: "Outra pessoa" },
      rascunhoCaso: { titulo: "Sigiloso" },
      clientesCache: [{ id: "c2", nome: "Outra pessoa" }],
    });

    const descartados = store.getState().vincularUsuario("user-1");
    expect(descartados).toBe(1);
    expect(store.getState()).toMatchObject({
      usuarioId: "user-1",
      fila: [],
      rascunhoCliente: {},
      rascunhoCaso: {},
      clientesCache: [],
    });
  });
});
