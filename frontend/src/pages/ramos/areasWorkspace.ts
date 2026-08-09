import { RAMOS, type FerramentaConfig, type RamoConfig } from "./ramosConfig";

export type AreaResumo = {
  slug: string;
  nome: string;
  ordem?: number;
  ativo?: boolean;
};

export type GrupoArea = {
  id: "pessoas" | "negocios" | "publico" | "especialidades";
  titulo: string;
  descricao: string;
  slugs: string[];
};

export type ResultadoFerramentaBusca = {
  areaSlug: string;
  areaTitulo: string;
  ferramenta: FerramentaConfig;
};

/**
 * Somente aliases técnicos em que a taxonomia de casos e o slug histórico do
 * workspace têm nomes diferentes. Especialidades canônicas NÃO são achatadas
 * em um núcleo pai: societário, sucessões e licitações preservam seu próprio
 * slug e, enquanto não houver workspace dedicado, permanecem sem hub.
 */
export const HUB_POR_AREA: Record<string, string> = {
  civil: "civel",
  criminal: "penal",
};

export const AREAS_PRINCIPAIS_PADRAO = [
  "ambiental",
  "empresarial",
  "trabalhista",
  "bancario",
  "tributario",
  "administrativo",
  "civil",
  "criminal",
] as const;

export const GRUPOS_AREAS: GrupoArea[] = [
  {
    id: "pessoas",
    titulo: "Pessoas e Patrimônio",
    descricao:
      "Relações privadas, família, patrimônio, consumo e proteção social.",
    slugs: [
      "civil",
      "consumidor",
      "familia",
      "sucessoes",
      "imobiliario",
      "previdenciario",
      "saude",
      "medico",
    ],
  },
  {
    id: "negocios",
    titulo: "Empresas e Negócios",
    descricao:
      "Estrutura empresarial, contratos, crédito, tributos e relações de trabalho.",
    slugs: [
      "empresarial",
      "societario",
      "contratual",
      "bancario",
      "tributario",
      "trabalhista",
      "digital_lgpd",
    ],
  },
  {
    id: "publico",
    titulo: "Poder Público e Regulação",
    descricao:
      "Administração, licitações, regulação, ambiente, trânsito e controle público.",
    slugs: [
      "administrativo",
      "licitacoes",
      "ambiental",
      "transito",
      "constitucional",
    ],
  },
  {
    id: "especialidades",
    titulo: "Especialidades",
    descricao: "Matérias com rito, fontes ou estratégia próprios.",
    slugs: ["criminal", "agrario", "agronegocio", "eleitoral", "internacional"],
  },
];

export function hubSlugDaArea(areaSlug: string): string | null {
  const slug = HUB_POR_AREA[areaSlug] ?? areaSlug;
  return RAMOS[slug] ? slug : null;
}

/**
 * Casos.tsx ainda não consome `?area=` para filtro nem para pré-preenchimento.
 * Estes caminhos são propositalmente honestos: não codificam um filtro que a
 * tela atual ignoraria. O workspace especializado continua sendo o caminho
 * contextual quando ele existe.
 */
export function novoCasoPath(): string {
  return "/casos/novo";
}

export function casosGeraisPath(): string {
  return "/casos";
}

export function importacaoPath(): string {
  return "/casos/novo?modo=documento";
}

export function normalizarBusca(valor: string): string {
  return valor
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function configDaArea(areaSlug: string): RamoConfig | undefined {
  const hubSlug = hubSlugDaArea(areaSlug);
  return hubSlug ? RAMOS[hubSlug] : undefined;
}

export function textoIndexavelDaArea(area: AreaResumo): string {
  const cfg = configDaArea(area.slug);
  const partes = [area.nome, area.slug];
  if (cfg) {
    partes.push(
      cfg.titulo,
      cfg.subtitulo,
      ...(cfg.subareas ?? []),
      ...cfg.ferramentas.flatMap((f) => [
        f.titulo,
        f.descricao,
        f.grupo ?? "",
        f.baseLegal,
      ]),
      ...(cfg.ferramentasExternas ?? []).flatMap((f) => [f.nome, f.descricao]),
    );
  }
  return normalizarBusca(partes.join(" "));
}

export function areaCombinaBusca(area: AreaResumo, termo: string): boolean {
  const q = normalizarBusca(termo);
  return !q || textoIndexavelDaArea(area).includes(q);
}

/**
 * Pesquisa ferramentas sem remover capacidades do Cível. O PR anterior
 * descartava grupos inteiros e, com eles, ferramentas sem equivalente em
 * Família/Consumidor/Imobiliário. A deduplicação aqui é apenas por endpoint
 * idêntico no resultado agregado da busca.
 */
export function buscarFerramentas(termo: string): ResultadoFerramentaBusca[] {
  const q = normalizarBusca(termo);
  if (!q) return [];
  const resultados: ResultadoFerramentaBusca[] = [];
  const endpoints = new Set<string>();

  for (const cfg of Object.values(RAMOS)) {
    for (const ferramenta of cfg.ferramentas) {
      const texto = normalizarBusca(
        [
          ferramenta.titulo,
          ferramenta.descricao,
          ferramenta.grupo ?? "",
          ferramenta.baseLegal,
          cfg.titulo,
        ].join(" "),
      );
      if (!texto.includes(q) || endpoints.has(ferramenta.endpoint)) continue;
      endpoints.add(ferramenta.endpoint);
      resultados.push({
        areaSlug: cfg.areaCaso,
        areaTitulo: cfg.titulo,
        ferramenta,
      });
    }
  }
  return resultados.slice(0, 12);
}

export function grupoDaArea(areaSlug: string): GrupoArea | undefined {
  return GRUPOS_AREAS.find((grupo) => grupo.slugs.includes(areaSlug));
}
