import type { RamoConfig } from "./ramosConfig";

export type WorkspaceTabId =
  "visao" | "casos" | "ferramentas" | "analise" | "referencias";

export type WorkspaceTab = {
  id: WorkspaceTabId;
  label: string;
};

export type RelacaoVisualArea = {
  slug: string;
  label: string;
  descricao: string;
  workspace?: string;
};

const COPIA_WORKSPACE: Record<string, { titulo?: string; subtitulo?: string }> =
  {
    civel: {
      titulo: "Direito Cível Geral",
      subtitulo:
        "Responsabilidade civil, obrigações, cobrança, indenizações e rito cível. Consumidor, Família e Imobiliário permanecem em workspaces próprios.",
    },
    empresarial: {
      subtitulo:
        "Empresas, governança, recuperação, operações societárias e contratos empresariais, com especialidades relacionadas preservadas na taxonomia.",
    },
    administrativo: {
      subtitulo:
        "Atos, sanções, servidores, contratos públicos e regulação. Licitações permanece classificação jurídica própria e relacionada.",
    },
    familia: {
      subtitulo:
        "Família, guarda, convivência, alimentos e divórcio. Sucessões permanece classificação jurídica própria e relacionada.",
    },
  };

const RELACOES_VISUAIS: Record<string, RelacaoVisualArea[]> = {
  civel: [
    {
      slug: "consumidor",
      label: "Consumidor",
      descricao: "Workspace próprio para relações de consumo e CDC.",
      workspace: "/areas-de-atuacao/consumidor",
    },
    {
      slug: "familia",
      label: "Família",
      descricao: "Workspace próprio para relações familiares.",
      workspace: "/areas-de-atuacao/familia",
    },
    {
      slug: "imobiliario",
      label: "Imobiliário",
      descricao:
        "Workspace próprio para locação, posse e negócios imobiliários.",
      workspace: "/areas-de-atuacao/imobiliario",
    },
  ],
  empresarial: [
    {
      slug: "societario",
      label: "Societário",
      descricao:
        "Classificação canônica própria; o núcleo empresarial oferece contexto e ferramentas correlatas sem reclassificar o caso.",
      workspace: "/areas-de-atuacao/societario",
    },
    {
      slug: "contratual",
      label: "Contratual",
      descricao:
        "Especialidade transversal; contratos podem pertencer a diferentes áreas conforme a relação jurídica.",
      workspace: "/areas-de-atuacao/contratual",
    },
  ],
  administrativo: [
    {
      slug: "licitacoes",
      label: "Licitações",
      descricao:
        "Classificação canônica própria, apresentada como especialidade relacionada ao Direito Administrativo.",
      workspace: "/areas-de-atuacao/licitacoes",
    },
  ],
  familia: [
    {
      slug: "sucessoes",
      label: "Sucessões",
      descricao:
        "Classificação canônica própria, apresentada como especialidade relacionada ao núcleo de Família.",
      workspace: "/areas-de-atuacao/sucessoes",
    },
  ],
};

const GUIAS: (keyof RamoConfig)[] = [
  "guiaBancario",
  "guiaTransito",
  "guiaTrabalhista",
  "guiaTributario",
  "guiaPrevidenciario",
  "guiaAmbiental",
  "guiaCivil",
  "guiaPenal",
  "guiaConsumidor",
  "guiaImobiliario",
  "guiaFamilia",
  "guiaAdministrativo",
  "guiaEmpresarial",
  "guiaLgpd",
];

export function areasDoWorkspace(cfg: RamoConfig): string[] {
  return [...new Set([cfg.areaCaso, ...(cfg.areasLegadas ?? [])])];
}

export function tituloDoWorkspace(cfg: RamoConfig): string {
  return COPIA_WORKSPACE[cfg.slug]?.titulo ?? cfg.titulo;
}

export function subtituloDoWorkspace(cfg: RamoConfig): string {
  return COPIA_WORKSPACE[cfg.slug]?.subtitulo ?? cfg.subtitulo;
}

export function relacoesDoWorkspace(cfg: RamoConfig): RelacaoVisualArea[] {
  return RELACOES_VISUAIS[cfg.slug] ?? [];
}

export function temFerramentasWorkspace(cfg: RamoConfig): boolean {
  return Boolean(
    cfg.ferramentas.length > 0 ||
    cfg.comparadorBacen ||
    cfg.liquidacaoTrabalhista ||
    cfg.tributarioFiscal ||
    cfg.previdenciarioSimulacao ||
    cfg.autosAmbientais ||
    cfg.ambientalEstrategia ||
    cfg.sociedadesCliente ||
    cfg.lgpdRegistros,
  );
}

export function temAnaliseWorkspace(cfg: RamoConfig): boolean {
  return Boolean(
    cfg.analiseDocumento || cfg.analiseExtratos || cfg.bancarioForense,
  );
}

export function temReferenciasWorkspace(cfg: RamoConfig): boolean {
  return Boolean(
    (cfg.subareas?.length ?? 0) > 0 ||
    (cfg.ferramentasExternas?.length ?? 0) > 0 ||
    GUIAS.some((chave) => Boolean(cfg[chave])),
  );
}

export function abasDoWorkspace(cfg: RamoConfig): WorkspaceTab[] {
  const abas: WorkspaceTab[] = [
    { id: "visao", label: "Visão geral" },
    { id: "casos", label: "Casos" },
  ];
  if (temFerramentasWorkspace(cfg)) {
    abas.push({ id: "ferramentas", label: "Ferramentas" });
  }
  if (temAnaliseWorkspace(cfg)) {
    abas.push({ id: "analise", label: "IA & Análise" });
  }
  abas.push({ id: "referencias", label: "Peças & referências" });
  return abas;
}

export function possuiRegistroEspecializado(cfg: RamoConfig): boolean {
  return !cfg.externo && Boolean(cfg.endpoint);
}
