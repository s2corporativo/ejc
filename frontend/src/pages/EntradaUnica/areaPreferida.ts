import { AREAS_CANONICAS } from "../ramos/areasWorkspace";

const AREAS_VALIDAS = new Set(AREAS_CANONICAS.map((area) => area.slug));

/**
 * Contexto opcional vindo de um workspace jurídico. Nunca aceita slug arbitrário:
 * somente uma das 25 classificações canônicas pode pré-selecionar o campo.
 * A escolha continua editável na confirmação humana da Entrada Jurídica.
 */
export function resolverAreaPreferida(valor: string | null): string | null {
  if (!valor) return null;
  return AREAS_VALIDAS.has(valor) ? valor : null;
}

/** Rótulo humano da área canônica; não inventa nome para slug desconhecido. */
export function rotuloAreaPreferida(slug: string): string {
  return AREAS_CANONICAS.find((area) => area.slug === slug)?.nome ?? slug;
}
