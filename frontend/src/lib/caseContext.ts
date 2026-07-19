/** Rotas e payloads contextuais compartilhados pelos fluxos de caso. */
export function caseJourneyPath(caseId: string): string {
  return `/casos/${encodeURIComponent(caseId)}/jornada`;
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
