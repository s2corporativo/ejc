// ── Cadastro Manual (sem IA) — fila offline de clientes/casos ────────────────
// Store zustand + persist (padrão de stores/preferences.ts). Guarda rascunhos
// dos formulários, uma fila de envios pendentes (criados sem conexão ou cuja
// requisição falhou por rede) e um cache id+nome de clientes para o select de
// caso funcionar offline.
//
// A função de transporte (POST) é INJETADA em `sincronizar`/`enviarDireto` —
// a página passa o axios central (lib/api.ts); os testes vitest passam um mock.
// Nenhuma instância axios paralela é criada aqui.
import { create } from "zustand";
import { persist } from "zustand/middleware";

/** Chave do localStorage — exportada para a limpeza no logout (stores/auth.ts). */
export const CADASTRO_MANUAL_KEY = "ejc_cadastro_manual";

export type TipoItem = "cliente" | "caso";
export type StatusItem = "pendente" | "enviando" | "erro";

export type ItemFila = {
  /** id LOCAL (crypto.randomUUID) — não é o id do backend. */
  id: string;
  tipo: TipoItem;
  payload: Record<string, unknown>;
  criado_em: string; // ISO
  status: StatusItem;
  erro?: string;
  /**
   * Dono do item (User.id no momento do enfileiramento). A fila persiste no
   * localStorage: sem o carimbo, a fila criada pelo usuário A seria enviada
   * com o token do usuário B na mesma estação. `vincularUsuario` descarta o
   * que não pertence ao usuário logado e `sincronizar` nunca envia item de
   * outro dono.
   */
  usuarioId?: string;
  /**
   * Quando um caso foi criado offline junto com um cliente novo, aponta para
   * o id LOCAL do item cliente ainda na fila. Ao sincronizar o cliente com
   * 2xx, `payload.client_id` do caso é substituído pelo id REAL retornado e
   * este campo é limpo.
   */
  clientePendenteId?: string;
};

export type ClienteCacheEntry = { id: string; nome: string };

/**
 * Transporte HTTP injetável. Deve lançar erros no formato axios
 * (`err.response.status` / `err.response.data.detail` / `err.code`) —
 * a página injeta `(path, body) => api.post(path, body).then(r => r.data)`.
 */
export type PostFn = (
  path: string,
  body: Record<string, unknown>,
) => Promise<{ id?: string }>;

export type SyncResultado = {
  /** Itens confirmados com 2xx e removidos da fila nesta rodada. */
  enviados: ItemFila[];
  /** Itens que terminaram a rodada em erro (4xx, ambíguo ou dependência). */
  comErro: number;
  /** Itens que continuam pendentes (rede indisponível / dependência pendente). */
  pendentes: number;
};

// ── Classificação de erro (duck-typing do erro axios; sem importar axios) ────
type ErroClassificado =
  { acao: "erro"; mensagem: string } | { acao: "pendente" };

export const MSG_AMBIGUO =
  "Resposta ambígua do servidor (timeout ou erro interno). Verifique manualmente no sistema se o registro foi criado antes de tentar de novo — evita duplicidade.";

function extrairDetail(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // Formato 422 do Pydantic: [{loc, msg, ...}]
    const msgs = detail
      .map((d) =>
        d && typeof d === "object" && "msg" in d
          ? String((d as { msg: unknown }).msg)
          : null,
      )
      .filter(Boolean);
    if (msgs.length) return msgs.join("; ");
  }
  return null;
}

export function classificarErro(err: unknown): ErroClassificado {
  const e = err as {
    response?: { status?: number; data?: unknown };
    code?: string;
  };
  const status = e?.response?.status;
  if (typeof status === "number") {
    if (status >= 400 && status < 500) {
      return {
        acao: "erro",
        mensagem:
          extrairDetail(e.response?.data) ??
          `Rejeitado pelo servidor (HTTP ${status}).`,
      };
    }
    // 5xx: chegou ao servidor mas o resultado é incerto — não re-enviar
    // automaticamente para não duplicar.
    return { acao: "erro", mensagem: MSG_AMBIGUO };
  }
  // Timeout do axios: a requisição PODE ter sido processada — ambíguo.
  if (e?.code === "ECONNABORTED" || e?.code === "ETIMEDOUT") {
    return { acao: "erro", mensagem: MSG_AMBIGUO };
  }
  // Sem resposta e sem timeout: rede fora — seguro re-tentar depois.
  return { acao: "pendente" };
}

function novoId(): string {
  // crypto.randomUUID existe em navegadores modernos e no jsdom/node ≥ 19;
  // fallback simples para ambientes sem a API (não precisa ser criptográfico).
  try {
    return crypto.randomUUID();
  } catch {
    return `local-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

export function descreverItem(item: ItemFila): string {
  const p = item.payload as {
    nome?: string;
    razao_social?: string;
    titulo?: string;
  };
  if (item.tipo === "cliente") {
    return p.nome || p.razao_social || "Cliente sem nome";
  }
  return p.titulo || "Caso sem título";
}

interface CadastroManualState {
  rascunhoCliente: Record<string, unknown>;
  rascunhoCaso: Record<string, unknown>;
  fila: ItemFila[];
  clientesCache: ClienteCacheEntry[];
  /** Dono do estado persistido (User.id) — ver vincularUsuario. */
  usuarioId: string | null;
  /** trava de reentrância do sync (não persistida). */
  sincronizando: boolean;

  /**
   * Vincula o estado persistido ao usuário logado. Se o estado pertencia a
   * OUTRO usuário (troca de conta na mesma estação), descarta fila, rascunhos
   * e cache — nada criado por A pode ser enviado com o token de B, e os
   * rascunhos carregam PII de A. Retorna quantos itens da fila foram
   * descartados (a página avisa com toast quando > 0).
   */
  vincularUsuario: (usuarioId: string) => number;
  setRascunhoCliente: (r: Record<string, unknown>) => void;
  setRascunhoCaso: (r: Record<string, unknown>) => void;
  limparRascunhoCliente: () => void;
  limparRascunhoCaso: () => void;
  setClientesCache: (clientes: ClienteCacheEntry[]) => void;

  /** Adiciona item à fila e retorna o id local gerado. */
  enfileirar: (
    tipo: TipoItem,
    payload: Record<string, unknown>,
    clientePendenteId?: string,
  ) => string;
  descartarItem: (id: string) => void;
  /** Volta um item 'erro' para 'pendente' (usado pelo "Tentar agora"). */
  reativarItem: (id: string) => void;

  /**
   * Processa a fila em ordem (clientes antes de casos dependentes). Só roda
   * nos gatilhos externos (mount, evento online, botão) — sem retry interno.
   */
  sincronizar: (post: PostFn) => Promise<SyncResultado>;
}

export const useCadastroManualStore = create<CadastroManualState>()(
  persist(
    (set, get) => ({
      rascunhoCliente: {},
      rascunhoCaso: {},
      fila: [],
      clientesCache: [],
      usuarioId: null,
      sincronizando: false,

      vincularUsuario: (usuarioId) => {
        const s = get();
        // Estado de OUTRO usuário (troca de conta na mesma estação, ou logout
        // que não limpou): descarta tudo — fila/rascunhos/cache têm PII do
        // dono anterior e a fila seria enviada com o token errado.
        if (s.usuarioId && s.usuarioId !== usuarioId) {
          const descartados = s.fila.length;
          set({
            usuarioId,
            fila: [],
            rascunhoCliente: {},
            rascunhoCaso: {},
            clientesCache: [],
          });
          return descartados;
        }
        // Defesa em profundidade: mesmo com o dono do estado correto, um item
        // carimbado com outro usuarioId nunca sobrevive.
        const proprios = s.fila.filter(
          (f) => !f.usuarioId || f.usuarioId === usuarioId,
        );
        const descartados = s.fila.length - proprios.length;
        set({
          usuarioId,
          ...(descartados > 0 ? { fila: proprios } : {}),
        });
        return descartados;
      },

      setRascunhoCliente: (rascunhoCliente) => set({ rascunhoCliente }),
      setRascunhoCaso: (rascunhoCaso) => set({ rascunhoCaso }),
      limparRascunhoCliente: () => set({ rascunhoCliente: {} }),
      limparRascunhoCaso: () => set({ rascunhoCaso: {} }),
      setClientesCache: (clientesCache) => set({ clientesCache }),

      enfileirar: (tipo, payload, clientePendenteId) => {
        const id = novoId();
        const dono = get().usuarioId;
        const item: ItemFila = {
          id,
          tipo,
          payload,
          criado_em: new Date().toISOString(),
          status: "pendente",
          ...(dono ? { usuarioId: dono } : {}),
          ...(clientePendenteId ? { clientePendenteId } : {}),
        };
        set((s) => ({ fila: [...s.fila, item] }));
        return id;
      },

      descartarItem: (id) =>
        set((s) => ({ fila: s.fila.filter((f) => f.id !== id) })),

      reativarItem: (id) =>
        set((s) => ({
          fila: s.fila.map((f) =>
            f.id === id && f.status === "erro"
              ? { ...f, status: "pendente", erro: undefined }
              : f,
          ),
        })),

      sincronizar: async (post) => {
        // Dedupe entre chamadas concorrentes: a segunda retorna sem tocar na fila.
        if (get().sincronizando) {
          return { enviados: [], comErro: 0, pendentes: 0 };
        }
        set({ sincronizando: true });
        const enviados: ItemFila[] = [];
        const marcar = (id: string, patch: Partial<ItemFila>) =>
          set((s) => ({
            fila: s.fila.map((f) => (f.id === id ? { ...f, ...patch } : f)),
          }));
        try {
          // Ordem: clientes primeiro (casos podem depender deles), depois
          // por criação. O snapshot só define a ORDEM; o estado de cada item
          // é relido na hora do envio (pega client_id já substituído).
          const ordem = [...get().fila].sort((a, b) => {
            if (a.tipo !== b.tipo) return a.tipo === "cliente" ? -1 : 1;
            return a.criado_em.localeCompare(b.criado_em);
          });

          for (const snapshot of ordem) {
            const item = get().fila.find((f) => f.id === snapshot.id);
            // Já removido (2xx em chamada anterior) ou em envio: não reenviar.
            if (!item || item.status !== "pendente") continue;

            // NUNCA envia item de outro dono com o token da sessão atual
            // (vincularUsuario já descarta; aqui é a garantia final).
            if (item.usuarioId && item.usuarioId !== get().usuarioId) continue;

            // Caso dependente de cliente ainda na fila.
            if (item.tipo === "caso" && item.clientePendenteId) {
              const dep = get().fila.find(
                (f) => f.id === item.clientePendenteId,
              );
              if (dep) {
                if (dep.status === "erro") {
                  // Comportamento documentado: dependente vira 'erro' VISÍVEL
                  // apontando o cliente que precisa de correção (nunca some).
                  marcar(item.id, {
                    status: "erro",
                    erro: `Aguardando correção do cliente pendente "${descreverItem(dep)}" — corrija/reenvie o cliente e tente novamente.`,
                  });
                }
                // dep pendente/enviando: o caso continua pendente nesta rodada.
                continue;
              }
              // Cliente vinculado foi descartado sem sincronizar: impossível
              // resolver o client_id — erro visível, decisão humana.
              marcar(item.id, {
                status: "erro",
                erro: "O cliente vinculado a este caso foi descartado da fila antes de ser enviado. Descarte este caso ou cadastre novamente.",
              });
              continue;
            }

            marcar(item.id, { status: "enviando", erro: undefined });
            try {
              const data = await post(
                item.tipo === "cliente" ? "/clients/" : "/cases/",
                item.payload,
              );
              // 2xx confirmado: só agora o item sai da fila.
              set((s) => ({ fila: s.fila.filter((f) => f.id !== item.id) }));
              enviados.push(item);
              if (item.tipo === "cliente") {
                const realId = data?.id;
                set((s) => ({
                  fila: s.fila.map((f) =>
                    f.tipo === "caso" && f.clientePendenteId === item.id
                      ? realId
                        ? {
                            ...f,
                            clientePendenteId: undefined,
                            payload: { ...f.payload, client_id: realId },
                            // O único erro possível aqui era o de dependência
                            // ("aguardando correção do cliente") — resolvido
                            // agora; volta a 'pendente' e segue nesta rodada.
                            status: "pendente" as const,
                            erro: undefined,
                          }
                        : {
                            ...f,
                            status: "erro" as const,
                            erro: "Cliente criado, mas o servidor não retornou o id. Verifique manualmente e recadastre o caso.",
                          }
                      : f,
                  ),
                }));
              }
            } catch (err) {
              const c = classificarErro(err);
              if (c.acao === "erro") {
                marcar(item.id, { status: "erro", erro: c.mensagem });
              } else {
                // Rede fora: volta a 'pendente' para o próximo gatilho.
                marcar(item.id, { status: "pendente", erro: undefined });
              }
            }
          }
        } finally {
          set({ sincronizando: false });
        }
        const fila = get().fila;
        return {
          enviados,
          comErro: fila.filter((f) => f.status === "erro").length,
          pendentes: fila.filter((f) => f.status === "pendente").length,
        };
      },
    }),
    {
      name: CADASTRO_MANUAL_KEY,
      version: 2,
      // v1 não carimbava o dono (usuarioId) — impossível provar a quem a
      // fila/rascunhos pertencem numa estação compartilhada. Descarta o
      // estado antigo em vez de arriscar enviar dados de A com o token de B.
      migrate: () => ({
        rascunhoCliente: {},
        rascunhoCaso: {},
        fila: [],
        clientesCache: [],
        usuarioId: null,
      }),
      partialize: (state) => ({
        rascunhoCliente: state.rascunhoCliente,
        rascunhoCaso: state.rascunhoCaso,
        // Itens 'enviando' interrompidos (fechou o app no meio) voltariam
        // presos; normaliza para 'pendente' já na escrita.
        fila: state.fila.map((f) =>
          f.status === "enviando" ? { ...f, status: "pendente" as const } : f,
        ),
        clientesCache: state.clientesCache,
        usuarioId: state.usuarioId,
      }),
    },
  ),
);

/**
 * Limpa TODO o estado do cadastro manual — memória e localStorage. Chamada no
 * LOGOUT (stores/auth.ts), como já acontece com o RASCUNHO_KEY do intake:
 * fila e rascunhos carregam PII e não podem sobreviver ao fim da sessão em
 * estação compartilhada (LGPD).
 */
export function limparCadastroManual(): void {
  useCadastroManualStore.setState({
    rascunhoCliente: {},
    rascunhoCaso: {},
    fila: [],
    clientesCache: [],
    usuarioId: null,
    sincronizando: false,
  });
  try {
    useCadastroManualStore.persist.clearStorage();
  } catch {
    // Storage indisponível não pode derrubar o logout.
  }
}
