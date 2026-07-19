// Testes da fila offline do Cadastro Manual (sem IA). O transporte HTTP é
// injetado como mock — nenhuma rede/axios real é usada.
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  CADASTRO_MANUAL_KEY,
  MSG_AMBIGUO,
  classificarErro,
  descreverItem,
  limparCadastroManual,
  useCadastroManualStore,
  type PostFn,
} from "./cadastroManual";

const store = useCadastroManualStore;

function resetStore() {
  store.setState({
    rascunhoCliente: {},
    rascunhoCaso: {},
    fila: [],
    clientesCache: [],
    usuarioId: null,
    sincronizando: false,
  });
}

/** Enfileira o par offline padrão: cliente novo + caso vinculado a ele. */
function enfileirarClienteECaso() {
  const idCliente = store
    .getState()
    .enfileirar("cliente", { tipo: "PF", nome: "Maria Silva" });
  const idCaso = store
    .getState()
    .enfileirar(
      "caso",
      { titulo: "Ação de cobrança", area: "civil", client_id: "" },
      idCliente,
    );
  return { idCliente, idCaso };
}

const erroHttp = (status: number, detail?: unknown) => ({
  response: { status, data: detail !== undefined ? { detail } : {} },
});
const erroRede = { request: {}, message: "Network Error" };

beforeEach(() => {
  resetStore();
});

describe("cadastroManual — fila offline", () => {
  it("(a) enfileira offline cliente e caso vinculado por clientePendenteId", () => {
    const { idCliente, idCaso } = enfileirarClienteECaso();
    const fila = store.getState().fila;
    expect(fila).toHaveLength(2);
    const cliente = fila.find((f) => f.id === idCliente)!;
    const caso = fila.find((f) => f.id === idCaso)!;
    expect(cliente.tipo).toBe("cliente");
    expect(cliente.status).toBe("pendente");
    expect(caso.tipo).toBe("caso");
    expect(caso.clientePendenteId).toBe(idCliente);
    expect(caso.criado_em).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(descreverItem(cliente)).toBe("Maria Silva");
    expect(descreverItem(caso)).toBe("Ação de cobrança");
  });

  it("(b) sync processa cliente ANTES do caso e substitui client_id pelo id real", async () => {
    enfileirarClienteECaso();
    const chamadas: Array<{ path: string; body: Record<string, unknown> }> = [];
    const post: PostFn = vi.fn(async (path, body) => {
      chamadas.push({ path, body });
      return { id: path === "/clients/" ? "real-cli-1" : "real-caso-1" };
    });

    const r = await store.getState().sincronizar(post);

    expect(chamadas.map((c) => c.path)).toEqual(["/clients/", "/cases/"]);
    expect(chamadas[1].body.client_id).toBe("real-cli-1");
    expect(store.getState().fila).toHaveLength(0);
    expect(r.enviados.map((i) => i.tipo)).toEqual(["cliente", "caso"]);
  });

  it("(b2) mesmo com o caso criado antes do cliente na fila, o cliente vai primeiro", async () => {
    // Ordem invertida de inserção: caso primeiro, cliente depois.
    const idCaso = store
      .getState()
      .enfileirar("caso", { titulo: "T", area: "civil", client_id: "" });
    const idCliente = store
      .getState()
      .enfileirar("cliente", { tipo: "PF", nome: "N" });
    // Religa o vínculo manualmente para o cenário.
    store.setState((s) => ({
      fila: s.fila.map((f) =>
        f.id === idCaso ? { ...f, clientePendenteId: idCliente } : f,
      ),
    }));
    const paths: string[] = [];
    const post: PostFn = async (path) => {
      paths.push(path);
      return { id: "x" };
    };
    await store.getState().sincronizar(post);
    expect(paths).toEqual(["/clients/", "/cases/"]);
    expect(store.getState().fila).toHaveLength(0);
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

  it("(c2) 422 do Pydantic (detail em lista) vira mensagem legível", () => {
    const c = classificarErro(
      erroHttp(422, [{ loc: ["body", "area"], msg: "Área inválida" }]),
    );
    expect(c).toEqual({ acao: "erro", mensagem: "Área inválida" });
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
      throw erroRede;
    });

    await store.getState().sincronizar(post);
    const fila = store.getState().fila;
    expect(fila).toHaveLength(1);
    expect(fila[0].status).toBe("pendente");
    expect(fila[0].erro).toBeUndefined();

    // Próximo gatilho re-tenta (não é retry automático — é nova chamada).
    await store.getState().sincronizar(post);
    expect(post).toHaveBeenCalledTimes(2);
  });

  it("(e) item só sai da fila após 2xx e sync concorrente não reenvia (dedupe)", async () => {
    store.getState().enfileirar("cliente", { tipo: "PF", nome: "Maria" });
    let resolver!: (v: { id: string }) => void;
    const post: PostFn = vi.fn(
      () => new Promise<{ id: string }>((res) => (resolver = res)),
    );

    const p1 = store.getState().sincronizar(post);
    // Envio em andamento: item marcado 'enviando' e AINDA na fila.
    expect(store.getState().fila[0].status).toBe("enviando");

    // Chamada concorrente: trava de reentrância — não dispara segundo POST.
    const r2 = await store.getState().sincronizar(post);
    expect(r2.enviados).toHaveLength(0);
    expect(post).toHaveBeenCalledTimes(1);

    resolver({ id: "real-1" });
    const r1 = await p1;
    expect(r1.enviados).toHaveLength(1);
    expect(store.getState().fila).toHaveLength(0);

    // Sync posterior sobre fila vazia não chama transporte.
    await store.getState().sincronizar(post);
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("(f) descartar remove o item da fila", () => {
    const id = store.getState().enfileirar("cliente", { tipo: "PF", nome: "X" });
    expect(store.getState().fila).toHaveLength(1);
    store.getState().descartarItem(id);
    expect(store.getState().fila).toHaveLength(0);
  });

  it("caso dependente de cliente com erro fica 'erro' visível apontando a dependência", async () => {
    const { idCliente, idCaso } = enfileirarClienteECaso();
    const post: PostFn = async (path) => {
      if (path === "/clients/") throw erroHttp(422, "PF requer nome");
      return { id: "nunca" };
    };

    await store.getState().sincronizar(post);
    const fila = store.getState().fila;
    expect(fila).toHaveLength(2);
    expect(fila.find((f) => f.id === idCliente)!.status).toBe("erro");
    const caso = fila.find((f) => f.id === idCaso)!;
    expect(caso.status).toBe("erro");
    expect(caso.erro).toContain("Aguardando correção do cliente pendente");
    expect(caso.erro).toContain("Maria Silva");
  });

  it("reativarItem volta 'erro' para 'pendente' e permite novo envio", async () => {
    const id = store.getState().enfileirar("cliente", { tipo: "PF", nome: "M" });
    const post: PostFn = vi
      .fn<PostFn>()
      .mockRejectedValueOnce(erroHttp(422, "CPF inválido"))
      .mockResolvedValueOnce({ id: "ok-1" });

    await store.getState().sincronizar(post);
    expect(store.getState().fila[0].status).toBe("erro");

    store.getState().reativarItem(id);
    expect(store.getState().fila[0].status).toBe("pendente");
    expect(store.getState().fila[0].erro).toBeUndefined();

    const r = await store.getState().sincronizar(post);
    expect(r.enviados).toHaveLength(1);
    expect(store.getState().fila).toHaveLength(0);
  });

  it("caso cujo cliente vinculado foi descartado vira 'erro' explicativo", async () => {
    const { idCliente, idCaso } = enfileirarClienteECaso();
    store.getState().descartarItem(idCliente);
    const post: PostFn = vi.fn(async () => ({ id: "x" }));

    await store.getState().sincronizar(post);
    const caso = store.getState().fila.find((f) => f.id === idCaso)!;
    expect(caso.status).toBe("erro");
    expect(caso.erro).toContain("descartado");
    expect(post).not.toHaveBeenCalled();
  });

  it("cliente corrigido e reenviado destrava o caso dependente na MESMA rodada", async () => {
    const { idCliente } = enfileirarClienteECaso();
    const post: PostFn = vi
      .fn<PostFn>()
      .mockRejectedValueOnce(erroHttp(422, "PF requer CPF"))
      .mockResolvedValueOnce({ id: "cli-real" })
      .mockResolvedValueOnce({ id: "caso-real" });

    // 1ª rodada: cliente 422 → ambos em erro (dependência).
    await store.getState().sincronizar(post);
    expect(store.getState().fila.every((f) => f.status === "erro")).toBe(true);

    // Correção + reativação do cliente; o caso NÃO precisa de ação manual.
    store.getState().reativarItem(idCliente);
    const r = await store.getState().sincronizar(post);

    expect(r.enviados.map((i) => i.tipo)).toEqual(["cliente", "caso"]);
    expect(store.getState().fila).toHaveLength(0);
    const corpoCaso = (post as ReturnType<typeof vi.fn>).mock.calls[2][1] as {
      client_id?: string;
    };
    expect(corpoCaso.client_id).toBe("cli-real");
  });
});

describe("cadastroManual — dono da fila (multiusuário na mesma estação)", () => {
  it("enfileirar carimba o item com o usuarioId vinculado", () => {
    store.getState().vincularUsuario("user-a");
    store.getState().enfileirar("cliente", { tipo: "PF", nome: "Maria" });
    expect(store.getState().fila[0].usuarioId).toBe("user-a");
  });

  it("vincularUsuario com OUTRO usuário descarta fila, rascunhos e cache", () => {
    store.getState().vincularUsuario("user-a");
    store.getState().setRascunhoCliente({ nome: "PII de A" });
    store.getState().setClientesCache([{ id: "c1", nome: "Cliente de A" }]);
    enfileirarClienteECaso();
    expect(store.getState().fila).toHaveLength(2);

    const descartados = store.getState().vincularUsuario("user-b");

    expect(descartados).toBe(2);
    const s = store.getState();
    expect(s.usuarioId).toBe("user-b");
    expect(s.fila).toHaveLength(0);
    expect(s.rascunhoCliente).toEqual({});
    expect(s.rascunhoCaso).toEqual({});
    expect(s.clientesCache).toEqual([]);
  });

  it("vincularUsuario com o MESMO usuário preserva a fila", () => {
    store.getState().vincularUsuario("user-a");
    enfileirarClienteECaso();
    const descartados = store.getState().vincularUsuario("user-a");
    expect(descartados).toBe(0);
    expect(store.getState().fila).toHaveLength(2);
  });

  it("sincronizar NUNCA envia item carimbado com outro usuarioId", async () => {
    // Estado adverso (defesa em profundidade): item de A sobrevivente com a
    // sessão de B ativa — o sync deve ignorá-lo, jamais enviá-lo.
    store.getState().vincularUsuario("user-a");
    store.getState().enfileirar("cliente", { tipo: "PF", nome: "PII de A" });
    store.setState({ usuarioId: "user-b" });
    const post: PostFn = vi.fn(async () => ({ id: "x" }));

    const r = await store.getState().sincronizar(post);

    expect(post).not.toHaveBeenCalled();
    expect(r.enviados).toHaveLength(0);
    expect(store.getState().fila).toHaveLength(1); // intocado (vincular descarta)
  });

  it("limparCadastroManual (logout) zera o estado e remove a chave persistida", () => {
    store.getState().vincularUsuario("user-a");
    store.getState().setRascunhoCliente({ nome: "PII" });
    enfileirarClienteECaso();
    localStorage.setItem(CADASTRO_MANUAL_KEY, '{"qualquer":"coisa"}');

    limparCadastroManual();

    const s = store.getState();
    expect(s.fila).toHaveLength(0);
    expect(s.rascunhoCliente).toEqual({});
    expect(s.usuarioId).toBeNull();
    expect(localStorage.getItem(CADASTRO_MANUAL_KEY)).toBeNull();
  });
});
