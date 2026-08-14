// ── Navegação canônica do modo caso (Fase 1 do plano de simplificação) ───────
// Fonte ÚNICA dos cinco destinos do caso: a barra persistente
// (CaseContextBar), a página do caso (CasoDetalhe/GROUPS) e o dock de ações
// (CaseCommandDock) derivam TODOS desta lista — os rótulos não podem divergir.
// As abas (?tab=...) continuam sendo a unidade de deep-link; cada seção apenas
// agrupa abas existentes. Nenhuma aba é removida — só reagrupada.
import {
  Activity,
  FileStack,
  LayoutDashboard,
  Scale,
  WalletCards,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface CaseNavSection {
  /** Rótulo canônico exibido na barra, na página e no dock. */
  label: string;
  /** Aba padrão aberta ao navegar para a seção. */
  tab: string;
  icon: LucideIcon;
  /** Descrição curta usada no CaseCommandDock. */
  descricao: string;
  /** Todas as abas (?tab=...) agrupadas nesta seção. */
  tabs: readonly string[];
  /** Rotas irmãs /casos/:id/* que pertencem à seção (realce na barra). */
  routeAliases?: readonly string[];
}

export const CASE_NAV_SECTIONS: readonly CaseNavSection[] = [
  {
    // Superfície de decisão: próxima ação do orquestrador + jornada embutida
    // + dados do caso. A antiga aba "orquestrador" foi promovida para cá.
    label: "Visão",
    tab: "resumo",
    icon: LayoutDashboard,
    descricao: "Próxima ação, jornada, alertas e dados do caso.",
    tabs: ["resumo", "partes", "etiquetas"],
    routeAliases: ["/jornada", "/entrevista"],
  },
  {
    // "Histórico e encerramento" (memoria) foi absorvido por Atividades.
    label: "Atividades",
    tab: "timeline",
    icon: Activity,
    descricao: "Linha do tempo, processos, prazos, audiências e memória.",
    tabs: [
      "timeline",
      "processos",
      "mensagens",
      "prazos",
      "audiencias",
      "checklists",
      "memoria",
    ],
  },
  {
    // Tela C (Bloco 3): "pecas" entra aqui — peça é o documento que o caso
    // produz, e a seção já reúne tudo que o caso guarda e gera em arquivo.
    // Duplicação temporária com o módulo /pecas aceita pelo titular
    // (Decisões de 2026-08-02, item 2).
    label: "Arquivos",
    tab: "documentos",
    icon: FileStack,
    descricao: "Documentos, peças, provas, contratos e procurações.",
    tabs: ["documentos", "pecas", "provas", "contratos", "procuracoes"],
  },
  {
    label: "Estratégia",
    // Fase 3 (QA / unificação): as 9 sub-abas anteriores foram consolidadas
    // em 4 — teses (com "Sugeridas pela IA"), indicadores (jurisprudência RAG,
    // precedentes, score e risco), dossiê e ferramentas (com IA Defensiva).
    tab: "teses",
    icon: Scale,
    descricao: "Teses, indicadores, dossiê e ferramentas de decisão jurídica.",
    tabs: ["teses", "indicadores", "dossie", "ferramentas"],
  },
  {
    label: "Financeiro",
    tab: "financeiro",
    icon: WalletCards,
    descricao: "Honorários, custos e liquidez do caso.",
    tabs: ["financeiro", "custos", "liquidez"],
  },
];

// Abas que deixaram de existir como destino próprio. O conteúdo do
// "orquestrador" foi promovido à Visão (aba resumo) — o deep-link antigo
// continua resolvendo via redirecionamento em CasoDetalhe.
// Fase 3 (QA / unificação): sub-abas de Estratégia consolidadas —
// deep-links antigos continuam resolvendo para a nova aba destino.
export const LEGACY_CASE_TAB_REDIRECTS: Record<string, string> = {
  orquestrador: "resumo",
  "teses-sugeridas": "teses",
  jurisprudencia: "indicadores",
  precedentes: "indicadores",
  score: "indicadores",
  risco: "indicadores",
  iaDefensive: "ferramentas",
};
