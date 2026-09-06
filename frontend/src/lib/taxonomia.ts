// ── Taxonomia de áreas derivada do backend (S1) ──────────────────────────────
// Única fonte no frontend para "quais são as áreas e como se chamam": tudo
// vem de `types/gerado.ts` (emitido por backend/scripts/gerar_tipos_frontend.py).
// Não mantenha listas locais de áreas em páginas — importe daqui.
//
// Nota: `lib/areaCatalog.ts` (fallback de GET /areas) está em PR aberto
// (#1387) e será apontado para cá quando aquele PR integrar.
import {
  AREAS_CANONICAS,
  AREAS_DESTAQUE,
  ROTULO_AREA,
  type CaseArea,
} from "../types/gerado";

export type { CaseArea };
export { AREAS_CANONICAS, AREAS_DESTAQUE, ROTULO_AREA };

export type AreaOpcao = { slug: CaseArea; nome: string };

/** Opções de área na ordem canônica do backend (para <select>/chips). */
export const AREAS_OPCOES: readonly AreaOpcao[] = AREAS_CANONICAS.map(
  (slug) => ({ slug, nome: ROTULO_AREA[slug] }),
);

/** Rótulo pt-BR de um slug; devolve o próprio slug se desconhecido. */
export function rotuloArea(slug?: string | null): string {
  if (!slug) return "";
  return (ROTULO_AREA as Record<string, string>)[slug] ?? slug;
}

/** Opções com as áreas de destaque (consumidor, cível) primeiro. */
export const AREAS_OPCOES_DESTAQUE: readonly AreaOpcao[] = [
  ...AREAS_DESTAQUE.map((slug) => ({ slug, nome: ROTULO_AREA[slug] })),
  ...AREAS_OPCOES.filter((a) => !AREAS_DESTAQUE.includes(a.slug)),
];
