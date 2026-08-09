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

export type WorkspaceTabId =
  "visao-geral" | "casos" | "ferramentas" | "analise" | "referencias";

export type ResultadoFerramentaBusca = {
  areaSlug: string;
  areaTitulo: string;
  ferramenta: FerramentaConfig;
};

/**
 * A taxonomia do banco continua intacta. Estes aliases alteram apenas a
 * arquitetura de informação: especialidades juridicamente subordinadas abrem
 * o workspace do núcleo correspondente sem reclassificar nenhum caso.
 */
export const HUB_POR_AREA: Record<string, string> = {
  civil: "civel",
  criminal: "penal",
  societario: "empresarial",
  sucessoes: "familia",
  licitacoes: "administrativo",
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
      "bancario",
      "tributario",
      "trabalhista",
      "digital_lgpd",
      "contratual",
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

export const ESPECIALIDADES_SUBORDINADAS: Record<
  string,
  { pai: string; rotulo: string }
> = {
  sucessoes: { pai: "familia", rotulo: "Sucessões" },
  societario: { pai: "empresarial", rotulo: "Societário" },
  licitacoes: { pai: "administrativo", rotulo: "Licitações" },
};

export function hubSlugDaArea(areaSlug: string): string | null {
  const slug = HUB_POR_AREA[areaSlug] ?? areaSlug;
  return RAMOS[slug] ? slug : null;
}

export function tituloDoWorkspace(cfg: RamoConfig): string {
  const titulos: Record<string, string> = {
    civel: "Direito Cível Geral",
    familia: "Família e Sucessões",
    empresarial: "Empresarial e Societário",
    administrativo: "Administrativo e Licitações",
  };
  return titulos[cfg.slug] ?? cfg.titulo;
}

export function subtituloDoWorkspace(cfg: RamoConfig): string {
  if (cfg.slug === "civel") {
    return "Responsabilidade civil · Obrigações · Cobrança · Indenizações · JEC";
  }
  return cfg.subtitulo;
}

/**
 * Cível permanece íntegro no backend para compatibilidade histórica, mas a
 * interface deixa de repetir ferramentas que já têm workspace dedicado.
 */
export function ferramentasDoWorkspace(cfg: RamoConfig): FerramentaConfig[] {
  if (cfg.slug !== "civel") return cfg.ferramentas;
  const gruposDelegados = new Set(["Consumidor", "Família", "Imobiliário"]);
  return cfg.ferramentas.filter(
    (f) => !f.grupo || !gruposDelegados.has(f.grupo),
  );
}

export function subareasDoWorkspace(cfg: RamoConfig): string[] {
  const subareas = cfg.subareas ?? [];
  if (cfg.slug !== "civel") return subareas;
  const termosDelegados = [
    "consum",
    "famíl",
    "famil",
    "invent",
    "sucess",
    "imobili",
    "usuc",
    "locaç",
    "locac",
    "condom",
  ];
  return subareas.filter((subarea) => {
    const texto = normalizarBusca(subarea);
    return !termosDelegados.some((termo) =>
      texto.includes(normalizarBusca(termo)),
    );
  });
}

export function abasDoWorkspace(cfg: RamoConfig): WorkspaceTabId[] {
  const abas: WorkspaceTabId[] = ["visao-geral", "casos"];
  const temFerramentasEspecializadas = Boolean(
    cfg.comparadorBacen ||
    cfg.bancarioForense ||
    cfg.liquidacaoTrabalhista ||
    cfg.tributarioFiscal ||
    cfg.previdenciarioSimulacao ||
    cfg.autosAmbientais ||
    cfg.ambientalEstrategia ||
    cfg.lgpdRegistros ||
    cfg.sociedadesCliente,
  );
  if (ferramentasDoWorkspace(cfg).length || temFerramentasEspecializadas) {
    abas.push("ferramentas");
  }
  if (cfg.analiseDocumento || cfg.analiseExtratos) abas.push("analise");
  if (
    subareasDoWorkspace(cfg).length ||
    (cfg.ferramentasExternas?.length ?? 0) > 0 ||
    cfg.guiaBancario ||
    cfg.guiaTransito ||
    cfg.guiaTrabalhista ||
    cfg.guiaTributario ||
    cfg.guiaPrevidenciario ||
    cfg.guiaAmbiental ||
    cfg.guiaCivil ||
    cfg.guiaPenal ||
    cfg.guiaConsumidor ||
    cfg.guiaImobiliario ||
    cfg.guiaFamilia ||
    cfg.guiaAdministrativo ||
    cfg.guiaEmpresarial ||
    cfg.guiaLgpd
  ) {
    abas.push("referencias");
  }
  return abas;
}

export function novoCasoPath(areaSlug: string): string {
  return `/casos/novo?area=${encodeURIComponent(areaSlug)}`;
}

export function casosDaAreaPath(areaSlug: string): string {
  return `/casos?area=${encodeURIComponent(areaSlug)}`;
}

export function importacaoDaAreaPath(areaSlug: string): string {
  return `/casos/novo?modo=documento&area=${encodeURIComponent(areaSlug)}`;
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
  const subordinada = ESPECIALIDADES_SUBORDINADAS[area.slug];
  const partes = [area.nome, area.slug, subordinada?.rotulo ?? ""];
  if (cfg) {
    partes.push(
      tituloDoWorkspace(cfg),
      subtituloDoWorkspace(cfg),
      ...subareasDoWorkspace(cfg),
      ...ferramentasDoWorkspace(cfg).flatMap((f) => [
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

export function buscarFerramentas(termo: string): ResultadoFerramentaBusca[] {
  const q = normalizarBusca(termo);
  if (!q) return [];
  const resultados: ResultadoFerramentaBusca[] = [];
  const endpoints = new Set<string>();

  for (const cfg of Object.values(RAMOS)) {
    for (const ferramenta of ferramentasDoWorkspace(cfg)) {
      const texto = normalizarBusca(
        [
          ferramenta.titulo,
          ferramenta.descricao,
          ferramenta.grupo ?? "",
          ferramenta.baseLegal,
          tituloDoWorkspace(cfg),
        ].join(" "),
      );
      if (!texto.includes(q) || endpoints.has(ferramenta.endpoint)) continue;
      endpoints.add(ferramenta.endpoint);
      resultados.push({
        areaSlug: cfg.slug,
        areaTitulo: tituloDoWorkspace(cfg),
        ferramenta,
      });
    }
  }
  return resultados.slice(0, 12);
}

export function grupoDaArea(areaSlug: string): GrupoArea | undefined {
  return GRUPOS_AREAS.find((grupo) => grupo.slugs.includes(areaSlug));
}
