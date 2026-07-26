// ── Rascunho recuperável do "novo caso por documento" ─────────────────────
// Persistência local (localStorage) do intake documental para que uma falha em
// qualquer passo — resolver cliente, criar caso, anexar documento ou aplicar a
// extração — NUNCA deixe o usuário sem forma de retomar. A criação do caso é um
// fluxo crítico: preferimos um rascunho recuperável a um caso parcial perdido.
//
// Regras de serialização:
//  - O File importado NÃO serializa em JSON → guardamos apenas nome/tipo; ao
//    retomar, o documento precisa ser reanexado (mensagem clara na UI).
//  - Chaves auxiliares do form começam com "_" (ex.: _arquivo_original,
//    _extracao). O snapshot remove todas elas e a extração viaja em campo
//    próprio (`extracao`), que é JSON puro e pode ser reaplicada no caso.
import type { ExtracaoPayload } from "./api";

/** Chave única do rascunho de intake documental no localStorage. */
export const RASCUNHO_KEY = "ejc_intake_rascunho";

/**
 * Validade do rascunho (48h). O rascunho carrega dados pessoais extraídos de
 * documentos — não deve viver indefinidamente no localStorage (LGPD). Passado
 * o TTL, `carregarRascunho()` descarta e limpa a chave.
 */
export const RASCUNHO_TTL_MS = 48 * 60 * 60 * 1000;

/** Snapshot serializável do fluxo "novo caso por documento". */
export interface IntakeRascunho {
  /** Campos do formulário do caso (sem chaves "_" nem o File). */
  form: Record<string, unknown>;
  /** Extração de IA já materializável no caso (JSON puro) — ou null. */
  extracao?: ExtracaoPayload | null;
  /** Nome do arquivo importado (o File em si não sobrevive à serialização). */
  arquivoNome?: string | null;
  /**
   * Lote da Entrada Universal (quando o intake veio de lote, sem File local —
   * os arquivos já estão no GED). Ausente em rascunhos antigos: compatível.
   */
  batchId?: string | null;
  /** Tipo do documento importado (tipo_key), quando informado. */
  arquivoTipo?: string | null;
  /** Título usado para o documento na GED. */
  tituloDoc?: string | null;
  /** id do cliente já resolvido/vinculado (quando aplicável). */
  clientId?: string | null;
  /** id do caso — `null` até o POST /cases/ concluir; não-null ⇒ não recriar. */
  caseId?: string | null;
  /** true quando o upload do documento já concluiu (um retry pula o upload). */
  uploadFeito?: boolean;
  /** epoch (ms) do último save — para exibir "há X" e ordenar. */
  salvoEm: number;
}

/** localStorage de forma tolerante (modo privado/SSR podem lançar). */
function storage(): Storage | null {
  try {
    return typeof localStorage !== "undefined" ? localStorage : null;
  } catch {
    return null;
  }
}

/**
 * Constrói o snapshot serializável do form: remove as chaves auxiliares "_"
 * (que carregam File/objetos de extração) e qualquer valor não-serializável.
 * Função pura — não toca em storage.
 */
export function snapshotForm(
  form: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(form || {})) {
    if (k.startsWith("_")) continue;
    if (v === undefined || v === null) continue;
    if (typeof v === "function") continue;
    if (typeof File !== "undefined" && v instanceof File) continue;
    out[k] = v;
  }
  return out;
}

/**
 * Persiste (ou substitui) o rascunho. `salvoEm` é carimbado aqui — o chamador
 * passa apenas o conteúdo. Falha de storage é silenciosa (o fluxo em memória
 * continua válido; apenas a recuperação pós-reload fica indisponível).
 */
export function salvarRascunho(
  rascunho: Omit<IntakeRascunho, "salvoEm">,
): void {
  const s = storage();
  if (!s) return;
  try {
    const payload: IntakeRascunho = { ...rascunho, salvoEm: Date.now() };
    s.setItem(RASCUNHO_KEY, JSON.stringify(payload));
  } catch {
    // Sem espaço/permissão: não interrompe a criação do caso.
  }
}

/** Lê o rascunho salvo; retorna null se ausente, malformado ou vencido (TTL). */
export function carregarRascunho(): IntakeRascunho | null {
  const s = storage();
  if (!s) return null;
  try {
    const raw = s.getItem(RASCUNHO_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return null;
    const obj = parsed as Partial<IntakeRascunho>;
    if (!obj.form || typeof obj.form !== "object") return null;
    // TTL: rascunho mais velho que 48h é descartado E removido do storage —
    // dados pessoais não ficam residentes indefinidamente na estação.
    if (
      typeof obj.salvoEm === "number" &&
      Date.now() - obj.salvoEm > RASCUNHO_TTL_MS
    ) {
      limparRascunho();
      return null;
    }
    return {
      form: obj.form as Record<string, unknown>,
      extracao: (obj.extracao ?? null) as ExtracaoPayload | null,
      arquivoNome: obj.arquivoNome ?? null,
      batchId: obj.batchId ?? null,
      arquivoTipo: obj.arquivoTipo ?? null,
      tituloDoc: obj.tituloDoc ?? null,
      clientId: obj.clientId ?? null,
      caseId: obj.caseId ?? null,
      uploadFeito: obj.uploadFeito ?? false,
      salvoEm: typeof obj.salvoEm === "number" ? obj.salvoEm : Date.now(),
    };
  } catch {
    return null;
  }
}

/**
 * Mescla um patch no rascunho existente e re-persiste (re-carimba `salvoEm`).
 * Se não houver rascunho, nada é feito e retorna null. Usado para avançar o
 * estado passo a passo (ex.: gravar `caseId` após criar o caso).
 */
export function atualizarRascunho(
  patch: Partial<IntakeRascunho>,
): IntakeRascunho | null {
  const atual = carregarRascunho();
  if (!atual) return null;
  const { salvoEm: _ignorado, ...conteudoAtual } = atual;
  const combinado = { ...conteudoAtual, ...patch };
  salvarRascunho(combinado);
  return carregarRascunho();
}

/** Remove o rascunho — chamar apenas no sucesso total ou ao descartar. */
export function limparRascunho(): void {
  const s = storage();
  if (!s) return;
  try {
    s.removeItem(RASCUNHO_KEY);
  } catch {
    // ignore
  }
}
