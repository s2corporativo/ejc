export type NovoCasoModo = "documento" | "manual";

/**
 * Entrada Jurídica é a única porta VISÍVEL para abertura de casos.
 * As rotas históricas continuam ativas para favoritos/deep-links, mas novos
 * atalhos devem convergir para /entrada e escolher apenas o modo da mesma porta.
 */
export const NOVO_CASO_DOCUMENTO_PATH = "/entrada?modo=documento";
export const NOVO_CASO_MANUAL_PATH = "/entrada?modo=manual";

export function entradaNovoCasoComCliente(
  clientId: string,
  modo: NovoCasoModo = "manual",
): string {
  const params = new URLSearchParams({ modo, client_id: clientId });
  return `/entrada?${params.toString()}`;
}

/**
 * Compatibilidade da rota histórica /casos/novo. Ela continua resolvendo os
 * modos existentes sem quebrar links antigos; nenhum novo CTA precisa apontar
 * para esta rota.
 */
export function resolverModoNovoCaso(
  pathname: string,
  search: string,
): NovoCasoModo | null {
  if (pathname !== "/casos/novo") return null;

  const modo = new URLSearchParams(search).get("modo");
  if (modo === "documento" || modo === "ia") return "documento";
  return "manual";
}
