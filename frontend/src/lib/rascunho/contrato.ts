// ── Contrato único de rascunho (Onda B — auditoria do SPA) ─────────────────
// O EJC tinha TRÊS mecanismos independentes de rascunho de entrada —
// lib/intakeRascunho (localStorage, TTL 48h), pages/EntradaUnica/rascunhoStorage
// (sessionStorage, só a sessão) e stores/cadastroManual (zustand persist) —
// com três implementações copiadas de "storage tolerante", chaves duplicadas
// entre arquivos e uma coordenação de logout incompleta: o caminho real de
// "Sair" (lib/api.ts → logout) limpava apenas o rascunho de intake, deixando
// PII do relato (sessionStorage) e da fila offline (localStorage) sobreviverem
// à sessão na mesma aba.
//
// Este módulo é a FONTE ÚNICA de três coisas:
//   1. As chaves/prefixos de cada rascunho (nada mais duplica string);
//   2. O acesso tolerante a storage (try/catch uma vez, não três);
//   3. O registro de limpeza: cada rascunho registra como se limpa e o logout
//      — onde quer que aconteça — chama UMA função (limparTodosRascunhos).
//
// O que NÃO é unificado de propósito: a política de retenção de cada fluxo
// (TTL 48h do intake documental vs. vida-de-sessão da Entrada Única vs. fila
// offline com dono no cadastro manual) é decisão de LGPD por entrada e fica
// no módulo de cada uma. Contrato = mecânica de storage e limpeza; adapter =
// cada módulo de domínio.

/** Chave do rascunho do intake documental ("novo caso por documento"). */
export const RASCUNHO_INTAKE_KEY = "ejc_intake_rascunho";

/**
 * Prefixo das chaves do rascunho da Entrada Única. O módulo usa duas chaves
 * derivadas — ponteiro ("ejc_entrada_rascunho_atual") e dados
 * ("ejc_entrada_rascunho:<id>") — e a limpeza varre o prefixo inteiro,
 * pegando também chaves órfãs de versões antigas.
 */
export const RASCUNHO_ENTRADA_PREFIXO = "ejc_entrada_rascunho";

/** Chave do estado persistido do cadastro manual (fila + rascunhos + cache). */
export const RASCUNHO_CADASTRO_MANUAL_KEY = "ejc_cadastro_manual";

/** localStorage de forma tolerante (modo privado/SSR podem lançar). */
export function storageLocal(): Storage | null {
  try {
    return typeof localStorage !== "undefined" ? localStorage : null;
  } catch {
    return null;
  }
}

/** sessionStorage de forma tolerante (mesmo contrato do storageLocal). */
export function storageSessao(): Storage | null {
  try {
    return typeof sessionStorage !== "undefined" ? sessionStorage : null;
  } catch {
    return null;
  }
}

/** Ação de limpeza registrada por cada módulo de rascunho. */
export type LimpezaRascunho = () => void;

const limpezas: LimpezaRascunho[] = [];

/**
 * Registra a limpeza do rascunho do módulo. Roda na carga do módulo (efeito
 * colateral de import): como um rascunho só EXISTE se seu módulo já carregou
 * nesta aba, a limpeza correspondente está sempre registrada quando precisa
 * rodar. Registrar duas vezes é inofensivo (dedupe por identidade).
 */
export function registrarLimpezaRascunho(fn: LimpezaRascunho): void {
  if (!limpezas.includes(fn)) limpezas.push(fn);
}

/**
 * Limpa TODOS os rascunhos registrados — o ponto único de coordenação do
 * logout. Falha de um item de storage não impede os demais (mesma tolerância
 * das gravações). Chamadores: lib/api.ts (logout HTTP) e stores/auth.ts
 * (401/403 e clearSession).
 */
export function limparTodosRascunhos(): void {
  for (const fn of limpezas) {
    try {
      fn();
    } catch {
      // Storage indisponível não pode derrubar o logout.
    }
  }
}

/** Visível para testes: esvazia o registro (entre testes isolados). */
export function _resetRegistroRascunhos(): void {
  limpezas.length = 0;
}
