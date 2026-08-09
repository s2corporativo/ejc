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
 * Catálogo visual das 25 classificações canônicas expostas pela API `/areas`.
 * Os slugs continuam sendo os do backend; este catálogo é fallback de UX e
 * não substitui a taxonomia persistida.
 */
export const AREAS_CANONICAS: AreaResumo[] = [
  ["empresarial", "Direito Empresarial"],
  ["civil", "Direito Cível"],
  ["criminal", "Direito Penal"],
  ["trabalhista", "Direito Trabalhista"],
  ["administrativo", "Direito Administrativo"],
  ["bancario", "Direito Bancário"],
  ["tributario", "Direito Tributário"],
  ["ambiental", "Direito Ambiental"],
  ["consumidor", "Direito do Consumidor"],
  ["familia", "Direito de Família"],
  ["sucessoes", "Direito das Sucessões"],
  ["imobiliario", "Direito Imobiliário"],
  ["previdenciario", "Direito Previdenciário"],
  ["saude", "Direito da Saúde"],
  ["medico", "Direito Médico"],
  ["digital_lgpd", "Direito Digital e LGPD"],
  ["transito", "Direito de Trânsito"],
  ["constitucional", "Direito Constitucional"],
  ["agrario", "Direito Agrário"],
  ["agronegocio", "Direito do Agronegócio"],
  ["eleitoral", "Direito Eleitoral"],
  ["internacional", "Direito Internacional"],
  ["contratual", "Direito Contratual"],
  ["societario", "Direito Societário"],
  ["licitacoes", "Licitações"],
].map(([slug, nome], index) => ({
  slug,
  nome,
  ordem: (index + 1) * 10,
}));

/**
 * Somente aliases técnicos em que a taxonomia de casos e o slug histórico do
 * workspace têm nomes diferentes. Especialidades canônicas NÃO são achatadas
 * em um núcleo pai.
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

const WORKSPACES_GERAIS = new Map<string, RamoConfig>();

function areaCanonica(areaSlug: string): AreaResumo | undefined {
  return AREAS_CANONICAS.find((area) => area.slug === areaSlug);
}

function temChavePropria(objeto: object, chave: PropertyKey): boolean {
  return Object.prototype.hasOwnProperty.call(objeto, chave);
}

function ramoRegistrado(slug: string): RamoConfig | undefined {
  return temChavePropria(RAMOS, slug) ? RAMOS[slug] : undefined;
}

function aliasDaArea(areaSlug: string): string | undefined {
  return temChavePropria(HUB_POR_AREA, areaSlug)
    ? HUB_POR_AREA[areaSlug]
    : undefined;
}

export function hubSlugDaArea(areaSlug: string): string | null {
  const alias = aliasDaArea(areaSlug);
  if (alias && ramoRegistrado(alias)) return alias;
  if (ramoRegistrado(areaSlug)) return areaSlug;
  return areaCanonica(areaSlug) ? areaSlug : null;
}

export function temWorkspaceEspecializado(areaSlug: string): boolean {
  return Boolean(ramoRegistrado(aliasDaArea(areaSlug) ?? areaSlug));
}

/**
 * Retorna a configuração especializada quando ela existe. Para as demais
 * classificações canônicas, cria e reutiliza uma casca estável de workspace:
 * Casos + Peças e referências centrais. Nenhum endpoint, ferramenta ou regra
 * jurídica é inventado para preencher a lacuna.
 */
export function configWorkspaceDaArea(
  areaSlug: string,
): RamoConfig | undefined {
  const direto = ramoRegistrado(areaSlug);
  if (direto) return direto;

  const alias = aliasDaArea(areaSlug);
  if (alias) {
    const porAlias = ramoRegistrado(alias);
    if (porAlias) return porAlias;
  }

  const area = areaCanonica(areaSlug);
  if (!area) return undefined;

  const existente = WORKSPACES_GERAIS.get(area.slug);
  if (existente) return existente;

  const workspace: RamoConfig = {
    slug: area.slug,
    endpoint: "",
    areaCaso: area.slug,
    titulo: area.nome,
    subtitulo:
      "Workspace geral desta especialidade: casos canônicos, peças e referências centrais do EJC. Ferramentas próprias só aparecem quando existe implementação confirmada.",
    icone: "Folder",
    cor: "slate",
    campoTitulo: "tipo",
    campoStatus: "status",
    campos: [],
    ferramentas: [],
    externo: true,
  };
  WORKSPACES_GERAIS.set(area.slug, workspace);
  return workspace;
}

/**
 * Casos.tsx ainda não consome `?area=` para filtro nem para pré-preenchimento.
 * Estes caminhos são propositalmente honestos: não codificam um filtro que a
 * tela atual ignoraria. O workspace é o caminho contextual de cada área.
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
  return configWorkspaceDaArea(areaSlug);
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
 * Pesquisa todas as ferramentas configuradas. Não deduplica por endpoint:
 * configurações diferentes podem compartilhar implementação HTTP e ainda ter
 * finalidade, defaults, base legal ou contexto jurídico distintos.
 */
export function buscarFerramentas(termo: string): ResultadoFerramentaBusca[] {
  const q = normalizarBusca(termo);
  if (!q) return [];
  const resultados: ResultadoFerramentaBusca[] = [];

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
      if (!texto.includes(q)) continue;
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
