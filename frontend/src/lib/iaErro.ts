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

/**
 * Extrai uma mensagem amigável de um erro de chamada de IA (axios).
 * Usa o `detail` do backend somente quando ele é leigo; senão devolve
 * o texto padrão (ou o `fallback` informado).
 */
// ── Erros das calculadoras dos ramos (Áreas de Atuação) ──────────────────────
/** Mensagem controlada para ferramenta bloqueada pelo backend (HTTP 503). */
export const MENSAGEM_FERRAMENTA_NAO_HOMOLOGADA =
  "Ferramenta temporariamente indisponível — em revisão jurídica. " +
  "Nenhum resultado é exibido até a homologação.";

/** Texto único do selo/aviso de ferramenta não homologada (badge, tooltip,
 * fallback do aviso da API) — evita divergência entre as telas. */
export const AVISO_FERRAMENTA_NAO_HOMOLOGADA =
  "Ferramenta não homologada — em revisão jurídica; resultado não deve ser usado profissionalmente.";

/**
 * Extrai mensagem amigável de erro das calculadoras de ramo.
 * Trata o bloqueio 503 `detail.codigo === "ferramenta_nao_homologada"` com
 * mensagem controlada (nunca erro genérico) e evita renderizar `detail`
 * objeto como filho React (crash).
 */
export function mensagemErroFerramenta(
  err: unknown,
  fallback: string = "Falha no cálculo",
): string {
  const resp = (
    err as
      | { response?: { status?: number; data?: { detail?: unknown } } }
      | undefined
  )?.response;
  const detail = resp?.data?.detail as
    | { codigo?: unknown; mensagem?: unknown }
    | string
    | undefined;
  if (
    resp?.status === 503 &&
    detail &&
    typeof detail === "object" &&
    detail.codigo === "ferramenta_nao_homologada"
  ) {
    return MENSAGEM_FERRAMENTA_NAO_HOMOLOGADA;
  }
  if (typeof detail === "string" && detail.trim()) return detail;
  if (
    detail &&
    typeof detail === "object" &&
    typeof detail.mensagem === "string"
  ) {
    return detail.mensagem;
  }
  return fallback;
}

export function mensagemErroIA(
  err: unknown,
  fallback: string = MENSAGEM_IA_INDISPONIVEL,
): string {
  const resp = (
    err as
      | { response?: { status?: number; data?: { detail?: unknown } } }
      | undefined
  )?.response;
  // 422 (validação Pydantic, detail em array) não é "IA indisponível":
  // orientar a revisar os dados em vez de mandar procurar o administrador.
  if (resp?.status === 422 && Array.isArray(resp?.data?.detail)) {
    return "Verifique os dados informados e tente novamente.";
  }
  const resposta = resp?.data;
  let detail: unknown = resposta?.detail;
  if (
    detail &&
    typeof detail === "object" &&
    typeof (detail as { mensagem?: unknown }).mensagem === "string"
  ) {
    detail = (detail as { mensagem: string }).mensagem;
  }
  if (
    typeof detail === "string" &&
    detail.trim() &&
    detail.length <= 400 &&
    !MARCADORES_TECNICOS.test(detail)
  ) {
    return detail;
  }
  return fallback;
}
