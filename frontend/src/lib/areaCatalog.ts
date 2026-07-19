/** Taxonomia estática usada como fallback quando GET /areas está indisponível. */
export type AreaDireito = { slug: string; nome: string; ordem?: number };

export const AREAS_FALLBACK: AreaDireito[] = [
  { slug: "civil", nome: "Cível" },
  { slug: "trabalhista", nome: "Trabalhista" },
  { slug: "consumidor", nome: "Consumidor" },
  { slug: "familia", nome: "Família" },
  { slug: "ambiental", nome: "Ambiental" },
  { slug: "criminal", nome: "Criminal" },
  { slug: "previdenciario", nome: "Previdenciário" },
  { slug: "empresarial", nome: "Empresarial" },
  { slug: "tributario", nome: "Tributário" },
  { slug: "administrativo", nome: "Administrativo" },
  { slug: "bancario", nome: "Bancário" },
  { slug: "imobiliario", nome: "Imobiliário" },
  { slug: "sucessoes", nome: "Sucessões" },
  { slug: "constitucional", nome: "Constitucional" },
  { slug: "digital_lgpd", nome: "Digital e LGPD" },
  { slug: "transito", nome: "Trânsito" },
  { slug: "saude", nome: "Saúde" },
  { slug: "medico", nome: "Médico" },
  { slug: "agrario", nome: "Agrário" },
  { slug: "agronegocio", nome: "Agronegócio" },
  { slug: "eleitoral", nome: "Eleitoral" },
  { slug: "internacional", nome: "Internacional" },
  { slug: "contratual", nome: "Contratual" },
  { slug: "societario", nome: "Societário" },
  { slug: "licitacoes", nome: "Licitações" },
];

const LABELS: Record<string, string> = Object.fromEntries(
  AREAS_FALLBACK.map((area) => [area.slug, area.nome]),
);

/** Rótulo PT-BR de um slug de área; devolve o próprio slug se desconhecido. */
export function areaLabel(slug?: string | null): string {
  if (!slug) return "";
  return LABELS[slug] ?? slug;
}
