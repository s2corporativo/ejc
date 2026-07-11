import { create } from "zustand";
import api from "../lib/api";

/**
 * Modo Caso — contexto global do caso ativo.
 *
 * O caso é ativado ao entrar em qualquer rota /casos/:id/* (ver
 * CaseContextBar, montado no Layout) e persiste em sessionStorage até o
 * usuário sair explicitamente (botão ✕ na faixa de contexto). Módulos
 * globais (Documentos, Peças, Prazos) usam o caso ativo como filtro
 * padrão quando a URL não traz `?caso=` — a URL sempre vence.
 */
export interface CasoAtivo {
  id: string;
  titulo: string;
  cliente?: string;
  numero_processo?: string;
}

const STORAGE_KEY = "ejc_caso_ativo";

function readStored(): CasoAtivo | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CasoAtivo;
    return parsed && typeof parsed.id === "string" && parsed.id
      ? parsed
      : null;
  } catch {
    return null;
  }
}

function persist(caso: CasoAtivo | null) {
  try {
    if (caso) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(caso));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage indisponível não deve derrubar o contexto em memória.
  }
}

interface CaseContextState {
  caso: CasoAtivo | null;
  /**
   * Ativa o caso pelo id (idempotente: não refaz nada se já é o ativo).
   * Busca título/nº do processo e, em segundo plano, o nome do cliente.
   */
  ativar: (id: string) => Promise<void>;
  /** Sai do modo caso (ação explícita do usuário). */
  sair: () => void;
}

// Token do último ativar() solicitado: em navegação rápida entre casos o GET
// antigo pode resolver por último — respostas obsoletas são descartadas para
// o caso ativo nunca divergir da rota atual.
let ultimoAtivarId: string | null = null;

export const useCaseContext = create<CaseContextState>((set, get) => ({
  caso: readStored(),
  ativar: async (id) => {
    if (!id || get().caso?.id === id) return;
    ultimoAtivarId = id;
    try {
      const { data } = await api.get(`/cases/${id}`);
      if (ultimoAtivarId !== id) return; // navegou para outro caso no meio
      const caso: CasoAtivo = {
        id,
        titulo: data?.titulo || "Caso",
        numero_processo:
          data?.numero_processo ||
          data?.processo_principal?.numero_cnj ||
          undefined,
      };
      persist(caso);
      set({ caso });
      if (data?.client_id) {
        // Nome do cliente carregado em segundo plano — falha silenciosa
        // (usuários sem acesso ao cadastro do cliente seguem sem o nome).
        api
          .get(`/clients/${data.client_id}`)
          .then((r) => {
            const nome = r.data?.nome || r.data?.razao_social;
            const atual = get().caso;
            if (!nome || atual?.id !== id) return;
            const next = { ...atual, cliente: nome };
            persist(next);
            set({ caso: next });
          })
          .catch(() => {});
      }
    } catch {
      // Sem acesso ao caso (RBAC) ou falha de rede: não ativa o modo caso.
    }
  },
  sair: () => {
    persist(null);
    set({ caso: null });
  },
}));
