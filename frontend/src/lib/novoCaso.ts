export type NovoCasoModo = "documento" | "manual";

export const NOVO_CASO_DOCUMENTO_PATH = "/casos/novo?modo=documento";
export const NOVO_CASO_MANUAL_PATH = "/casos/novo?modo=manual";

/**
 * Mantém a rota histórica /casos/novo como cadastro manual e permite abrir
 * diretamente o intake documental sem criar um módulo ou menu paralelo.
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
