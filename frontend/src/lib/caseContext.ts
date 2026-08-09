/** Rotas e payloads contextuais compartilhados pelos fluxos de caso. */
export function caminhoAbaCaso(idCaso: string, aba = "resumo"): string {
  return `/casos/${encodeURIComponent(idCaso)}?tab=${encodeURIComponent(aba)}`;
}

/**
 * A Jornada deixou de ser página operacional separada: novos links apontam
 * diretamente para a Visão do Caso. A rota histórica /casos/:id/jornada segue
 * registrada apenas como adapter/redirect para favoritos antigos.
 */
export function caseJourneyPath(caseId: string): string {
  return caminhoAbaCaso(caseId, "resumo");
}

export function readCaseContext(params: URLSearchParams): string | undefined {
  return params.get("caso")?.trim() || undefined;
}

export function addCaseContext<T extends Record<string, unknown>>(
  payload: T,
  caseId?: string | null,
): T & { case_id?: string } {
  const normalized = caseId?.trim();
  return normalized ? { ...payload, case_id: normalized } : { ...payload };
}
