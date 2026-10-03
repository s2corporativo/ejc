/** Taxonomia estática usada como fallback quando GET /areas está indisponível. */
export type AreaDireito = { slug: string; nome: string; ordem?: number };

/** Fonte única dos slugs, com apresentações e ordens históricas preservadas. */
export const AREA_CATALOG = [
  {
    slug: "civil",
    nome: "Cível",
    nomeWorkspace: "Direito Cível",
    ordemWorkspace: 20,
  },
  {
    slug: "trabalhista",
    nome: "Trabalhista",
    nomeWorkspace: "Direito Trabalhista",
    ordemWorkspace: 40,
  },
  {
    slug: "consumidor",
    nome: "Consumidor",
    nomeWorkspace: "Direito do Consumidor",
    ordemWorkspace: 90,
  },
  {
    slug: "familia",
    nome: "Família",
    nomeWorkspace: "Direito de Família",
    ordemWorkspace: 100,
  },
  {
    slug: "ambiental",
    nome: "Ambiental",
    nomeWorkspace: "Direito Ambiental",
    ordemWorkspace: 80,
  },
  {
    slug: "criminal",
    nome: "Criminal",
    nomeWorkspace: "Direito Penal",
    ordemWorkspace: 30,
  },
  {
    slug: "previdenciario",
    nome: "Previdenciário",
    nomeWorkspace: "Direito Previdenciário",
    ordemWorkspace: 130,
  },
  {
    slug: "empresarial",
    nome: "Empresarial",
    nomeWorkspace: "Direito Empresarial",
    ordemWorkspace: 10,
  },
  {
    slug: "tributario",
    nome: "Tributário",
    nomeWorkspace: "Direito Tributário",
    ordemWorkspace: 70,
  },
  {
    slug: "administrativo",
    nome: "Administrativo",
    nomeWorkspace: "Direito Administrativo",
    ordemWorkspace: 50,
  },
  {
    slug: "bancario",
    nome: "Bancário",
    nomeWorkspace: "Direito Bancário",
    ordemWorkspace: 60,
  },
  {
    slug: "imobiliario",
    nome: "Imobiliário",
    nomeWorkspace: "Direito Imobiliário",
    ordemWorkspace: 120,
  },
  {
    slug: "sucessoes",
    nome: "Sucessões",
    nomeWorkspace: "Direito das Sucessões",
    ordemWorkspace: 110,
  },
  {
    slug: "constitucional",
    nome: "Constitucional",
    nomeWorkspace: "Direito Constitucional",
    ordemWorkspace: 180,
  },
  {
    slug: "digital_lgpd",
    nome: "Digital e LGPD",
    nomeWorkspace: "Direito Digital e LGPD",
    ordemWorkspace: 160,
  },
  {
    slug: "transito",
    nome: "Trânsito",
    nomeWorkspace: "Direito de Trânsito",
    ordemWorkspace: 170,
  },
  {
    slug: "saude",
    nome: "Saúde",
    nomeWorkspace: "Direito da Saúde",
    ordemWorkspace: 140,
  },
  {
    slug: "medico",
    nome: "Médico",
    nomeWorkspace: "Direito Médico",
    ordemWorkspace: 150,
  },
  {
    slug: "agrario",
    nome: "Agrário",
    nomeWorkspace: "Direito Agrário",
    ordemWorkspace: 190,
  },
  {
    slug: "agronegocio",
    nome: "Agronegócio",
    nomeWorkspace: "Direito do Agronegócio",
    ordemWorkspace: 200,
  },
  {
    slug: "eleitoral",
    nome: "Eleitoral",
    nomeWorkspace: "Direito Eleitoral",
    ordemWorkspace: 210,
  },
  {
    slug: "internacional",
    nome: "Internacional",
    nomeWorkspace: "Direito Internacional",
    ordemWorkspace: 220,
  },
  {
    slug: "contratual",
    nome: "Contratual",
    nomeWorkspace: "Direito Contratual",
    ordemWorkspace: 230,
  },
  {
    slug: "societario",
    nome: "Societário",
    nomeWorkspace: "Direito Societário",
    ordemWorkspace: 240,
  },
  {
    slug: "licitacoes",
    nome: "Licitações",
    nomeWorkspace: "Licitações",
    ordemWorkspace: 250,
  },
];

export const AREAS_FALLBACK: AreaDireito[] = AREA_CATALOG.map(
  ({ slug, nome }) => ({ slug, nome }),
);

const LABELS: Record<string, string> = Object.fromEntries(
  AREAS_FALLBACK.map((area) => [area.slug, area.nome]),
);

/** Rótulo PT-BR de um slug de área; devolve o próprio slug se desconhecido. */
export function areaLabel(slug?: string | null): string {
  if (!slug) return "";
  return LABELS[slug] ?? slug;
}
