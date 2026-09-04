// ── Tradução de erros de IA para linguagem leiga ─────────────────────────────
// Erros de infraestrutura de IA (".env", "GROQ_API_KEY", "Ollama indisponível",
// "Todos os provedores falharam para task=…") NUNCA devem chegar ao advogado.
// `mensagemErroIA` deixa passar apenas `detail` do backend que seja legível
// por leigo; qualquer marcador técnico cai na mensagem padrão.

export const MENSAGEM_IA_INDISPONIVEL =
  "A inteligência artificial não está disponível no momento. " +
  "Tente novamente em instantes ou procure o administrador do sistema.";

/** Rótulo curto para tooltips/botões desabilitados de IA. */
export const ROTULO_IA_NAO_ATIVADA = "IA não ativada — procure o administrador";

// Marcadores de dialeto de infraestrutura que denunciam mensagem técnica.
const MARCADORES_TECNICOS =
  /\.env|provider|provedor(es)?\s+falhar|api[_\s-]?key|apikey|ollama|groq|openai|anthropic|task\s*=|errno|traceback|timeout|localhost|https?:\/\/|configure\s|nao configurad|não configurad|indispon[ií]vel:\s*\[/i;

// ── Erros das calculadoras dos ramos (Áreas de Atuação) ──────────────────────
/** Mensagem controlada para ferramenta bloqueada pelo backend (HTTP 503). */
export const MENSAGEM_FERRAMENTA_NAO_HOMOLOGADA =
  "Ferramenta temporariamente indisponível — em revisão jurídica. " +
  "Nenhum resultado é exibido até a homologação.";

/** Texto único do selo/aviso de ferramenta não homologada (badge, tooltip,
 * fallback do aviso da API) — evita divergência entre as telas. */
export const AVISO_FERRAMENTA_NAO_HOMOLOGADA =
  "Ferramenta não homologada — em revisão jurídica; resultado não deve ser usado profissionalmente.";

// ── Exportação do demonstrativo de cálculo (POST /pecas/demonstrativo) ───────
// O backend mantém a exportação atrás da flag PECAS_DEMONSTRATIVO_CALCULADORA_
// ENABLED (default OFF) e responde **403** quando ela está desligada. Não há
// endpoint de capacidades que exponha essa flag ao frontend — `/pecas/meta` só
// devolve tipos/áreas/níveis —, então o único caminho honesto é degradar bem no
// 403 em vez de vazar o texto cru do gate (que cita auditoria e data interna).
/** Bloqueio administrativo da exportação (flag desligada no backend). */
export const MENSAGEM_DEMONSTRATIVO_INDISPONIVEL =
  "Demonstrativo de cálculo indisponível: as regras da calculadora ainda não " +
  "foram homologadas. O resultado permanece na tela como apoio, sob revisão do advogado.";

/** 403 por papel (allowlist EQUIPE_JURIDICA) — motivo diferente do anterior. */
export const MENSAGEM_DEMONSTRATIVO_SEM_PERMISSAO =
  "Seu perfil não tem permissão para gerar demonstrativos de cálculo.";

// O backend usa 403 para DOIS motivos distintos nesta rota: falta de permissão
// ("Acesso negado", de requer_equipe_juridica) e a trava de homologação. O
// texto do gate de homologação sempre cita a exportação/as calculadoras; o de
// permissão, não. Sem essa separação o advogado receberia "sem permissão"
// quando o problema é a flag — e vice-versa.
const MARCADOR_DEMONSTRATIVO_BLOQUEADO = /demonstrativ|calculadora|homologa/i;

/**
 * Erro do POST /pecas/demonstrativo em linguagem de advogado.
 * Trata o 403 da trava de homologação e o 403 de papel com mensagens próprias;
 * qualquer outro status cai no tratamento comum das calculadoras.
 */
export function mensagemErroDemonstrativo(
  err: unknown,
  fallback: string = "Falha ao salvar o demonstrativo em Peças.",
): string {
  const { status, detail } = detailDaResposta(err);
  if (status === 403) {
    const texto =
      typeof detail === "string" ? detail : (mensagemObjeto(detail) ?? "");
    return MARCADOR_DEMONSTRATIVO_BLOQUEADO.test(texto)
      ? MENSAGEM_DEMONSTRATIVO_INDISPONIVEL
      : MENSAGEM_DEMONSTRATIVO_SEM_PERMISSAO;
  }
  return mensagemErroFerramenta(err, fallback);
}

/** `true` quando o erro é a trava administrativa (flag OFF) — a tela usa isso
 * para desabilitar o botão em vez de deixar o advogado tentar de novo. */
export function ehBloqueioDeExportacaoDemonstrativo(err: unknown): boolean {
  const { status, detail } = detailDaResposta(err);
  if (status !== 403) return false;
  const texto =
    typeof detail === "string" ? detail : (mensagemObjeto(detail) ?? "");
  return MARCADOR_DEMONSTRATIVO_BLOQUEADO.test(texto);
}

/**
 * Traduz o `detail` array do Pydantic (422 de validação) em orientação útil.
 * Nunca devolve objeto nem concatena payload arbitrário do servidor.
 */
function mensagemValidacao(detail: unknown[]): string {
  const generica = "Verifique os dados informados e tente novamente.";
  const primeiro = detail[0];
  if (!primeiro || typeof primeiro !== "object") return generica;
  const { loc, msg } = primeiro as { loc?: unknown; msg?: unknown };
  const campo = Array.isArray(loc)
    ? [...loc].reverse().find((p) => typeof p === "string" && p !== "query")
    : undefined;
  const texto = typeof msg === "string" && msg.trim() ? msg.trim() : "";
  if (typeof campo === "string" && campo) {
    const rotulo = campo.replace(/_/g, " ");
    return texto ? `Verifique o campo ${rotulo}: ${texto}` : generica;
  }
  return texto ? `Verifique os dados informados: ${texto}` : generica;
}

function detailDaResposta(err: unknown): {
  status?: number;
  detail?: unknown;
} {
  const response = (
    err as
      | { response?: { status?: number; data?: { detail?: unknown } } }
      | undefined
  )?.response;
  return { status: response?.status, detail: response?.data?.detail };
}

function mensagemObjeto(detail: unknown): string | null {
  if (!detail || typeof detail !== "object" || Array.isArray(detail))
    return null;
  const mensagem = (detail as { mensagem?: unknown }).mensagem;
  return typeof mensagem === "string" && mensagem.trim()
    ? mensagem.trim()
    : null;
}

function mensagemSegura(texto: string): string | null {
  const value = texto.trim();
  if (!value || value.length > 400 || MARCADORES_TECNICOS.test(value))
    return null;
  return value;
}

/**
 * Normalizador genérico para erros HTTP exibidos em superfícies jurídicas.
 * Aceita somente formas conhecidas: `detail` string, `detail.mensagem` e array
 * de validação Pydantic. Conteúdo técnico ou objeto arbitrário cai no fallback.
 */
export function mensagemErroHttp(err: unknown, fallback: string): string {
  const { status, detail } = detailDaResposta(err);
  if (status === 422 && Array.isArray(detail)) return mensagemValidacao(detail);
  if (typeof detail === "string") return mensagemSegura(detail) ?? fallback;
  const mensagem = mensagemObjeto(detail);
  return mensagem ? (mensagemSegura(mensagem) ?? fallback) : fallback;
}

/**
 * Extrai mensagem amigável de erro das calculadoras de ramo.
 * Trata o bloqueio 503 `detail.codigo === "ferramenta_nao_homologada"` com
 * mensagem controlada e delega as demais formas ao normalizador HTTP comum.
 */
export function mensagemErroFerramenta(
  err: unknown,
  fallback: string = "Falha no cálculo",
): string {
  const response = (
    err as
      | { response?: { status?: number; data?: { detail?: unknown } } }
      | undefined
  )?.response;
  const detail = response?.data?.detail;
  if (
    response?.status === 503 &&
    detail &&
    typeof detail === "object" &&
    !Array.isArray(detail) &&
    (detail as { codigo?: unknown }).codigo === "ferramenta_nao_homologada"
  ) {
    return MENSAGEM_FERRAMENTA_NAO_HOMOLOGADA;
  }
  return mensagemErroHttp(err, fallback);
}

/**
 * Extrai uma mensagem amigável de um erro de chamada de IA (axios).
 * Usa o `detail` do backend somente quando ele é leigo; senão devolve
 * o texto padrão (ou o `fallback` informado).
 */
export function mensagemErroIA(
  err: unknown,
  fallback: string = MENSAGEM_IA_INDISPONIVEL,
): string {
  const { status, detail } = detailDaResposta(err);
  if (status === 422 && Array.isArray(detail)) {
    return "Verifique os dados informados e tente novamente.";
  }
  if (typeof detail === "string") return mensagemSegura(detail) ?? fallback;
  const mensagem = mensagemObjeto(detail);
  return mensagem ? (mensagemSegura(mensagem) ?? fallback) : fallback;
}
