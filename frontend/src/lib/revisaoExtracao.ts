// ── FLX-048 — revisão de extração recuperável pós-refresh ─────────────────
// Helpers puros do fluxo "novo caso por documento": quando o preview (dry-run)
// da extração fica pendente de decisão, a URL recebe ?revisao=<caseId> e o
// rascunho do intake (lib/intakeRascunho) permanece no localStorage. Um F5
// nesse momento reconstrói o preview a partir do rascunho em vez de perder a
// decisão. Funções puras — testáveis sem router/storage.
import type { ExtracaoPayload } from "./api";
import type { IntakeRascunho } from "./intakeRascunho";

/** URL da lista de casos com a revisão pendente marcada (sobrevive a F5). */
export function urlRevisaoPendente(caseId: string): string {
  return `/casos?revisao=${encodeURIComponent(caseId)}`;
}

/**
 * O rascunho persistido cobre a revisão marcada na URL? Exige o MESMO caseId
 * e uma extração materializável — qualquer divergência significa que não há
 * o que recuperar (o param deve ser removido em silêncio).
 */
export function rascunhoCobreRevisao(
  rascunho: IntakeRascunho | null,
  caseId: string,
): rascunho is IntakeRascunho & { extracao: ExtracaoPayload } {
  return !!rascunho && rascunho.caseId === caseId && !!rascunho.extracao;
}

/** Remove apenas o param `revisao` da URL, preservando os demais. */
export function urlSemParamRevisao(pathname: string, search: string): string {
  const params = new URLSearchParams(search);
  params.delete("revisao");
  const query = params.toString();
  return `${pathname}${query ? `?${query}` : ""}`;
}
