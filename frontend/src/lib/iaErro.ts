// ── Tradução de erros de IA para linguagem leiga ─────────────────────────────
// Erros de infraestrutura de IA (".env", "GROQ_API_KEY", "Ollama indisponível",
// "Todos os provedores falharam para task=…") NUNCA devem chegar ao advogado.
// `mensagemErroIA` deixa passar apenas `detail` do backend que seja legível
// por leigo; qualquer marcador técnico cai na mensagem padrão.

export const MENSAGEM_IA_INDISPONIVEL =
  "A inteligência artificial não está disponível no momento. " +
  "Tente novamente em instantes ou procure o administrador do sistema.";

/** Rótulo curto para tooltips/botões desabilitados de IA. */
export const ROTULO_IA_NAO_ATIVADA =
  "IA não ativada — procure o administrador";

// Marcadores de dialeto de infraestrutura que denunciam mensagem técnica.
const MARCADORES_TECNICOS =
  /\.env|provider|provedor(es)?\s+falhar|api[_\s-]?key|apikey|ollama|groq|openai|anthropic|task\s*=|errno|traceback|timeout|localhost|https?:\/\/|configure\s|nao configurad|não configurad|indispon[ií]vel:\s*\[/i;

/**
 * Extrai uma mensagem amigável de um erro de chamada de IA (axios).
 * Usa o `detail` do backend somente quando ele é leigo; senão devolve
 * o texto padrão (ou o `fallback` informado).
 */
export function mensagemErroIA(
  err: unknown,
  fallback: string = MENSAGEM_IA_INDISPONIVEL,
): string {
  const resposta = (
    err as { response?: { data?: { detail?: unknown } } } | undefined
  )?.response?.data;
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
