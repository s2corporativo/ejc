export const CANONICAL_ROUTES = {
  dashboard: "/",
  clientes: "/clientes",
  casos: "/casos",
  atividades: "/atividades",
  documentos: "/documentos",
  pecas: "/pecas",
  inteligencia: "/inteligencia",
  areasAtuacao: "/areas-de-atuacao",
  financeiro: "/financeiro",
  configuracoes: "/configuracoes",
} as const;

export type LegacyCanonicalRedirect = {
  from: string;
  to: string;
  reason: string;
};

export const LEGACY_CANONICAL_REDIRECTS: LegacyCanonicalRedirect[] = [
  {
    from: "/prazos",
    to: "/atividades?tipo=prazo",
    reason: "Prazos foram consolidados na Central de Agenda e Prazos.",
  },
  {
    from: "/tarefas",
    to: "/atividades?tipo=tarefa",
    reason: "Tarefas foram consolidadas na Central de Agenda e Prazos.",
  },
  {
    from: "/intimacoes",
    to: "/atividades?tipo=intimacao",
    reason: "Intimações foram consolidadas na Central de Agenda e Prazos.",
  },
  {
    from: "/suspensoes",
    to: "/atividades?tipo=suspensao",
    reason: "Suspensões foram consolidadas na Central de Agenda e Prazos.",
  },
  {
    from: "/knowledge-hub",
    to: "/inteligencia?tab=conhecimento",
    reason: "Conhecimento Jurídico foi consolidado em Pesquisa e IA.",
  },
  {
    from: "/ramos",
    to: "/areas-de-atuacao",
    reason: "Ramos do Direito passou a se chamar Áreas de Atuação.",
  },
];
