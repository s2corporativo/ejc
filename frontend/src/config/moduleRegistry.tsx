import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import {
  Activity,
  AlarmClock,
  BarChart3,
  Bell,
  BookOpen,
  Bot,
  Briefcase,
  CalendarClock,
  CheckSquare,
  FileSignature,
  FileText,
  Filter,
  FolderOpen,
  Gavel,
  GitBranch,
  Inbox,
  LayoutDashboard,
  LayoutGrid,
  ListChecks,
  Newspaper,
  Plus,
  Scale,
  ScrollText,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";

export const ROLES = {
  gestores: ["superadmin", "admin", "socio"],
  administradores: ["superadmin", "admin"],
  financeiro: ["superadmin", "admin", "socio", "financeiro"],
  juridico: [
    "superadmin",
    "admin",
    "socio",
    "advogado",
    "advogado_auxiliar",
    "estagiario",
  ],
  compliance: ["superadmin", "admin", "socio", "advogado"],
} as const;

export type ModuleStatus = "active" | "beta" | "legacy" | "hidden";

export type ModuleRoute = {
  key: string;
  path: string;
  label: string;
  description: string;
  group: string;
  icon: LucideIcon;
  component: LazyExoticComponent<ComponentType>;
  roles?: readonly string[];
  showInNav?: boolean;
  end?: boolean;
  order?: number;
  status?: ModuleStatus;
  helpKey?: string;
  usesAI?: boolean;
  sensitive?: boolean;
  backendPrefixes?: string[];
  dependencies?: string[];
};

export type LegacyRedirect = {
  from: string;
  to: string;
  reason: string;
};

const Dashboard = lazy(() => import("../pages/Dashboard"));
const Clientes = lazy(() => import("../pages/Clientes"));
const DossieCliente = lazy(() => import("../pages/DossieCliente"));
const Casos = lazy(() => import("../pages/Casos"));
const CasoDetalhe = lazy(() => import("../pages/CasoDetalhe"));
const SalaDeGuerra = lazy(() => import("../pages/SalaDeGuerra"));
const EntrevistaInteligente = lazy(
  () => import("../pages/EntrevistaInteligente"),
);
const Prazos = lazy(() => import("../pages/Prazos"));
const Suspensoes = lazy(() => import("../pages/Suspensoes"));
const Tarefas = lazy(() => import("../pages/Tarefas"));
const Intimacoes = lazy(() => import("../pages/Intimacoes"));
const CentralAtividades = lazy(() => import("../pages/CentralAtividades"));
const GestaoDocumental = lazy(() => import("../pages/GestaoDocumental"));
const Pecas = lazy(() => import("../pages/Pecas"));
const RamosHub = lazy(() => import("../pages/RamosHub"));
const RamoBase = lazy(() => import("../pages/ramos/RamoBase"));
const CentralRelacionamento = lazy(
  () => import("../pages/CentralRelacionamento"),
);
const CRMLeads = lazy(() => import("../pages/CRMLeads"));
const FinanceiroWorkspace = lazy(() => import("../pages/FinanceiroWorkspace"));
const InteligenciaWorkspace = lazy(
  () => import("../pages/InteligenciaWorkspace"),
);
const Conhecimento = lazy(() => import("../pages/Conhecimento"));
const GovernancaIA = lazy(() => import("../pages/GovernancaIA"));
const KnowledgeHub = lazy(() => import("../pages/KnowledgeHub"));
const Biblioteca = lazy(() => import("../pages/Biblioteca"));
const MemoriaInstitucional = lazy(
  () => import("../pages/MemoriaInstitucional"),
);
const Wiki = lazy(() => import("../pages/Wiki"));
const DataJudBusca = lazy(() => import("../pages/DataJudBusca"));
const DiarioOficial = lazy(() => import("../pages/DiarioOficial"));
const RadarRegulatorio = lazy(() => import("../pages/RadarRegulatorio"));
const RadarCompliance = lazy(() => import("../pages/RadarCompliance"));
const Noticias = lazy(() => import("../pages/Noticias"));
const Checklists = lazy(() => import("../pages/Checklists"));
const Workflow = lazy(() => import("../pages/Workflow"));
const Assinaturas = lazy(() => import("../pages/Assinaturas"));
const Prompts = lazy(() => import("../pages/Prompts"));
const Produtividade = lazy(() => import("../pages/Produtividade"));
const Auditoria = lazy(() => import("../pages/Auditoria"));
const MapaModulos = lazy(() => import("../pages/MapaModulos"));
const Configuracoes = lazy(() => import("../pages/Configuracoes"));
const Usuarios = lazy(() => import("../pages/Usuarios"));
const Lixeira = lazy(() => import("../pages/Lixeira"));
const Ajuda = lazy(() => import("../pages/Ajuda"));
const Whatsapp = lazy(() => import("../pages/Whatsapp"));
const JornadaCaso = lazy(() => import("../pages/JornadaCaso"));

// DECISÃO: menu centrado no caso — o grupo "Principal" destaca Novo Caso e
// Casos logo abaixo do Dashboard; os demais módulos foram reagrupados em
// 5 famílias SEM alterar nenhum path existente (usuários têm rotas salvas).
export const MODULE_GROUP_ORDER = [
  "Principal",
  "Inteligência Jurídica",
  "Produção",
  "Gestão",
  "Financeiro",
  "Administração",
] as const;

export const STAFF_ROUTES: ModuleRoute[] = [
  {
    key: "dashboard",
    path: "/",
    label: "Dashboard",
    description: "Visão executiva da operação jurídica.",
    group: "Principal",
    icon: LayoutDashboard,
    component: Dashboard,
    showInNav: true,
    end: true,
    order: 10,
    helpKey: "dashboard",
    sensitive: false,
    backendPrefixes: ["/api/dashboard", "/api/health"],
  },
  // Destaque primário: wizard guiado de abertura de caso (cliente → caso).
  // Rota nova aditiva — /casos/novo vence /casos/:id no ranking do router v6.
  {
    key: "caso-novo",
    path: "/casos/novo",
    label: "Novo Caso",
    description:
      "Abertura guiada de caso: cliente (dedup por CPF/CNPJ) e dados básicos.",
    group: "Principal",
    icon: Plus,
    component: Casos,
    showInNav: true,
    order: 20,
    helpKey: "casos",
    sensitive: true,
    backendPrefixes: ["/api/cases", "/api/clients"],
  },
  {
    key: "relacionamento",
    path: "/central-relacionamento",
    label: "Relacionamento",
    description: "Visão consolidada de atendimento, captação e conversão.",
    group: "Gestão",
    icon: CalendarClock,
    component: CentralRelacionamento,
    roles: ROLES.gestores,
    showInNav: true,
    order: 10,
    helpKey: "atendimento",
    sensitive: true,
    backendPrefixes: ["/api/analytics", "/api/clients", "/api/notifications"],
  },
  {
    key: "crm",
    path: "/crm-leads",
    label: "Funil de Leads",
    description: "Captação, qualificação e conversão de leads.",
    group: "Gestão",
    icon: Users,
    component: CRMLeads,
    showInNav: true,
    order: 20,
    helpKey: "crm",
    sensitive: true,
    backendPrefixes: ["/api/clients"],
  },
  {
    key: "clientes",
    path: "/clientes",
    label: "Clientes",
    description: "Cadastro central de clientes e responsáveis.",
    group: "Gestão",
    icon: Briefcase,
    component: Clientes,
    showInNav: true,
    order: 30,
    helpKey: "clientes",
    sensitive: true,
    backendPrefixes: ["/api/clients", "/api/dossie-cliente"],
  },
  {
    key: "cliente-detalhe",
    path: "/clientes/:clientId",
    label: "Dossiê do Cliente",
    description: "Detalhes e histórico do cliente.",
    group: "Gestão",
    icon: Briefcase,
    component: DossieCliente,
    helpKey: "clientes",
    status: "hidden",
    sensitive: true,
  },
  {
    key: "cliente-dossie-alias",
    path: "/clientes/:clientId/dossie",
    label: "Dossiê do Cliente",
    description: "Alias compatível do dossiê do cliente.",
    group: "Gestão",
    icon: Briefcase,
    component: DossieCliente,
    helpKey: "clientes",
    status: "hidden",
    sensitive: true,
  },
  {
    key: "casos",
    path: "/casos",
    label: "Casos e Processos",
    description: "Gestão jurídica central de casos e processos.",
    group: "Principal",
    icon: Gavel,
    component: Casos,
    showInNav: true,
    order: 30,
    helpKey: "casos",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/cases", "/api/processes"],
  },
  {
    key: "caso-detalhe",
    path: "/casos/:id",
    label: "Detalhe do Caso",
    description: "Workspace contextual do caso.",
    group: "Principal",
    icon: Gavel,
    component: CasoDetalhe,
    helpKey: "casos",
    status: "hidden",
    sensitive: true,
  },
  // Rota-detalhe (padrão /casos/:id): jornada guiada das 9 etapas do caso.
  // status hidden = fora do menu, igual a caso-detalhe e sala-de-guerra.
  {
    key: "caso-jornada",
    path: "/casos/:id/jornada",
    label: "Jornada do Caso",
    description:
      "Linha de etapas do caso, da entrada do cliente à gestão contínua.",
    group: "Principal",
    icon: GitBranch,
    component: JornadaCaso,
    helpKey: "casos",
    status: "hidden",
    sensitive: true,
  },
  // Etapa 2 da jornada (Triagem): entrevista em texto livre com painel de
  // confiança da IA. status hidden = fora do menu, igual a caso-jornada.
  {
    key: "caso-entrevista",
    path: "/casos/:id/entrevista",
    label: "Entrevista Inteligente",
    description:
      "Relato livre do ocorrido com triagem preliminar da IA e confiança por item.",
    group: "Principal",
    icon: Filter,
    component: EntrevistaInteligente,
    helpKey: "casos",
    status: "hidden",
    sensitive: true,
    usesAI: true,
    // Backend exige advogado+ — sem o gate aqui, perfis de apoio navegavam
    // até a tela e só viam o 403 ao clicar em "Analisar".
    roles: ROLES.compliance,
    backendPrefixes: ["/api/triagem"],
  },
  {
    key: "sala-de-guerra",
    path: "/casos/:caseId/sala-de-guerra",
    label: "Sala de Guerra",
    description: "Estratégia vinculada a um caso específico.",
    group: "Principal",
    icon: ShieldAlert,
    component: SalaDeGuerra,
    helpKey: "casos",
    status: "hidden",
    sensitive: true,
    usesAI: true,
  },
  {
    key: "ramos",
    path: "/ramos",
    label: "Ramos do Direito",
    description: "Ferramentas jurídicas organizadas por área.",
    group: "Inteligência Jurídica",
    icon: Scale,
    component: RamosHub,
    showInNav: true,
    order: 30,
    helpKey: "ramos",
    usesAI: true,
    sensitive: true,
  },
  {
    key: "ramo-detalhe",
    path: "/ramos/:slug",
    label: "Núcleo Jurídico",
    description: "Ferramentas especializadas do ramo selecionado.",
    group: "Inteligência Jurídica",
    icon: Scale,
    component: RamoBase,
    helpKey: "ramos",
    status: "hidden",
    usesAI: true,
    sensitive: true,
  },
  {
    key: "atividades",
    path: "/atividades",
    label: "Agenda e Atividades",
    description: "Visão unificada de prazos, tarefas, intimações e eventos.",
    group: "Gestão",
    icon: CalendarClock,
    component: CentralAtividades,
    showInNav: true,
    order: 40,
    helpKey: "atividades",
    sensitive: true,
    backendPrefixes: ["/api/atividades", "/api/agenda-eventos"],
  },
  {
    key: "prazos",
    path: "/prazos",
    label: "Prazos",
    description: "Controle jurídico de prazos e confirmações.",
    group: "Gestão",
    icon: AlarmClock,
    component: Prazos,
    showInNav: true,
    order: 50,
    helpKey: "prazos",
    sensitive: true,
    backendPrefixes: ["/api/deadlines"],
  },
  {
    key: "tarefas",
    path: "/tarefas",
    label: "Tarefas",
    description: "Execução operacional atribuída à equipe.",
    group: "Gestão",
    icon: CheckSquare,
    component: Tarefas,
    showInNav: true,
    order: 60,
    helpKey: "tarefas",
    sensitive: true,
    backendPrefixes: ["/api/tasks"],
  },
  {
    key: "intimacoes",
    path: "/intimacoes",
    label: "Intimações",
    description: "Comunicações processuais e conferência jurídica.",
    group: "Gestão",
    icon: Inbox,
    component: Intimacoes,
    showInNav: true,
    order: 70,
    helpKey: "intimacoes",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/intimacoes"],
  },
  {
    key: "suspensoes",
    path: "/suspensoes",
    label: "Suspensões",
    description: "Suspensões processuais e reflexos em prazos.",
    group: "Gestão",
    icon: Activity,
    component: Suspensoes,
    showInNav: true,
    order: 80,
    helpKey: "prazos",
    sensitive: true,
    backendPrefixes: ["/api/suspensoes"],
  },
  {
    key: "documentos",
    path: "/documentos",
    label: "Documentos e Data Room",
    description: "Gestão documental e compartilhamento controlado.",
    group: "Produção",
    icon: FolderOpen,
    component: GestaoDocumental,
    showInNav: true,
    order: 10,
    helpKey: "documentos",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/documents", "/api/data-room", "/api/documentos-ia"],
  },
  {
    key: "pecas",
    path: "/pecas",
    label: "Peças Jurídicas",
    description: "Produção, validação, revisão e aprovação de peças.",
    group: "Produção",
    icon: FileText,
    component: Pecas,
    showInNav: true,
    order: 20,
    helpKey: "pecas",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/legal-docs", "/api/templates"],
  },
  {
    key: "assinaturas",
    path: "/assinaturas",
    label: "Assinaturas",
    description: "Solicitações, signatários e trilha de assinatura.",
    group: "Produção",
    icon: FileSignature,
    component: Assinaturas,
    showInNav: true,
    order: 30,
    helpKey: "assinaturas",
    sensitive: true,
    backendPrefixes: ["/api/signatures"],
  },
  {
    key: "workflow",
    path: "/workflow",
    label: "Workflows",
    description: "Fluxos, etapas e SLAs por área jurídica.",
    group: "Produção",
    icon: GitBranch,
    component: Workflow,
    showInNav: true,
    order: 40,
    helpKey: "workflow",
    sensitive: true,
    backendPrefixes: ["/api/workflow"],
  },
  {
    key: "checklists",
    path: "/checklists",
    label: "Checklists",
    description: "Listas de verificação vinculadas à produção.",
    group: "Produção",
    icon: ListChecks,
    component: Checklists,
    showInNav: true,
    order: 50,
    helpKey: "checklists",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/checklists"],
  },
  {
    key: "inteligencia",
    path: "/inteligencia",
    label: "Inteligência Jurídica",
    description: "Agentes, análise, validação, jurimetria e conhecimento.",
    group: "Inteligência Jurídica",
    icon: Sparkles,
    component: InteligenciaWorkspace,
    roles: ROLES.juridico,
    showInNav: true,
    order: 10,
    helpKey: "inteligencia",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/ai", "/api/ai-core", "/api/ai-skills"],
  },
  {
    key: "knowledge-hub",
    path: "/knowledge-hub",
    label: "Conhecimento Jurídico",
    description: "Busca unificada em RAG, teses, jurisprudência e memória.",
    group: "Inteligência Jurídica",
    icon: BookOpen,
    component: KnowledgeHub,
    showInNav: true,
    order: 20,
    helpKey: "conhecimento",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/rag", "/api/teses", "/api/jurisprudencias"],
  },
  {
    key: "biblioteca",
    path: "/biblioteca",
    label: "Biblioteca Jurídica",
    description: "Teses, peças de referência e memória institucional.",
    group: "Inteligência Jurídica",
    icon: BookOpen,
    component: Biblioteca,
    helpKey: "conhecimento",
    status: "hidden",
    sensitive: true,
    usesAI: true,
  },
  {
    key: "memoria",
    path: "/memoria",
    label: "Memória Institucional",
    description: "Resultados, aprendizados e precedentes internos.",
    group: "Inteligência Jurídica",
    icon: BookOpen,
    component: MemoriaInstitucional,
    helpKey: "conhecimento",
    status: "hidden",
    sensitive: true,
    usesAI: true,
  },
  {
    key: "wiki",
    path: "/wiki",
    label: "Wiki",
    description: "Conteúdo interno de apoio operacional.",
    group: "Inteligência Jurídica",
    icon: BookOpen,
    component: Wiki,
    helpKey: "conhecimento",
    status: "hidden",
    sensitive: true,
  },
  {
    key: "conhecimento-curadoria",
    path: "/conhecimento",
    label: "Curadoria RAG",
    description: "Ingestão e curadoria da base vetorial.",
    group: "Administração",
    icon: BookOpen,
    component: Conhecimento,
    roles: ROLES.gestores,
    helpKey: "conhecimento",
    status: "hidden",
    sensitive: true,
    usesAI: true,
  },
  {
    key: "prompts",
    path: "/prompts",
    label: "Prompts Operacionais",
    description: "Modelos de instrução reutilizáveis pela equipe.",
    group: "Inteligência Jurídica",
    icon: Bot,
    component: Prompts,
    roles: ROLES.juridico,
    helpKey: "inteligencia",
    status: "hidden",
    sensitive: true,
    usesAI: true,
  },
  {
    key: "datajud",
    path: "/datajud",
    label: "Consulta DataJud",
    description: "Consulta e sincronização de dados processuais do CNJ.",
    group: "Inteligência Jurídica",
    icon: Scale,
    component: DataJudBusca,
    showInNav: true,
    order: 40,
    helpKey: "datajud",
    sensitive: true,
    backendPrefixes: ["/api/v1/datajud"],
  },
  {
    key: "diario-oficial",
    path: "/diario-oficial",
    label: "Diário Oficial",
    description: "Palavras-chave, publicações e alertas monitorados.",
    group: "Inteligência Jurídica",
    icon: ScrollText,
    component: DiarioOficial,
    showInNav: true,
    order: 50,
    helpKey: "diario-oficial",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/diario-oficial"],
  },
  {
    key: "radar-regulatorio",
    path: "/radar-regulatorio",
    label: "Radar Regulatório",
    description: "Visão executiva dos alertas normativos.",
    group: "Inteligência Jurídica",
    icon: Bell,
    component: RadarRegulatorio,
    showInNav: true,
    order: 60,
    helpKey: "radar-regulatorio",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/v1/regulatorio"],
  },
  {
    key: "radar-compliance",
    path: "/compliance/radar",
    label: "Radar de Compliance",
    description: "Avaliação de riscos regulatórios e conformidade.",
    group: "Inteligência Jurídica",
    icon: ShieldAlert,
    component: RadarCompliance,
    roles: ROLES.compliance,
    showInNav: true,
    order: 70,
    helpKey: "compliance",
    sensitive: true,
    usesAI: true,
  },
  {
    key: "noticias",
    path: "/noticias",
    label: "Notícias Jurídicas",
    description: "Atualizações e conteúdo jurídico externo.",
    group: "Inteligência Jurídica",
    icon: Newspaper,
    component: Noticias,
    showInNav: true,
    order: 80,
    helpKey: "noticias",
    sensitive: false,
  },
  {
    key: "financeiro",
    path: "/financeiro",
    label: "Financeiro e Sociedade",
    description: "Honorários, despesas, contratos e gestão societária.",
    group: "Financeiro",
    icon: Wallet,
    component: FinanceiroWorkspace,
    roles: ROLES.financeiro,
    showInNav: true,
    order: 10,
    helpKey: "financeiro",
    sensitive: true,
    backendPrefixes: ["/api/financeiro", "/api/fees", "/api/despesas"],
  },
  {
    key: "produtividade",
    path: "/produtividade",
    label: "Produtividade",
    description: "Indicadores operacionais da equipe.",
    group: "Administração",
    icon: BarChart3,
    component: Produtividade,
    showInNav: true,
    order: 10,
    helpKey: "produtividade",
    sensitive: true,
  },
  {
    key: "configuracoes",
    path: "/configuracoes",
    label: "Preferências",
    description: "Aparência, navegação, segurança e preferências pessoais.",
    group: "Administração",
    icon: Settings,
    component: Configuracoes,
    showInNav: true,
    order: 20,
    helpKey: "configuracoes",
    sensitive: false,
  },
  {
    key: "administracao-configuracoes",
    path: "/administracao/configuracoes",
    label: "Administração do EJC",
    description:
      "Governança institucional e acesso aos painéis administrativos.",
    group: "Administração",
    icon: Settings,
    component: Configuracoes,
    roles: ROLES.administradores,
    showInNav: true,
    order: 30,
    helpKey: "configuracoes",
    sensitive: true,
  },
  {
    key: "governanca-ia",
    path: "/ia-governanca",
    label: "Governança da IA",
    description: "Curadoria, fontes, prompts sistêmicos e guardrails.",
    group: "Administração",
    icon: Sparkles,
    component: GovernancaIA,
    roles: ROLES.gestores,
    showInNav: true,
    order: 40,
    helpKey: "governanca-ia",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/ia-governanca"],
  },
  {
    key: "auditoria",
    path: "/auditoria",
    label: "Auditoria",
    description: "Trilha imutável de ações críticas.",
    group: "Administração",
    icon: ShieldCheck,
    component: Auditoria,
    roles: ROLES.gestores,
    showInNav: true,
    order: 50,
    helpKey: "auditoria",
    sensitive: true,
    backendPrefixes: ["/api/audit"],
  },
  {
    key: "mapa-modulos",
    path: "/mapa-modulos",
    label: "Mapa de Módulos",
    description: "Inventário técnico e funcional do EJC.",
    group: "Administração",
    icon: LayoutGrid,
    component: MapaModulos,
    roles: ROLES.gestores,
    showInNav: true,
    order: 60,
    helpKey: "autofix",
    sensitive: false,
    status: "beta",
    backendPrefixes: ["/api/system-modules"],
  },
  {
    key: "usuarios",
    path: "/usuarios",
    label: "Usuários e Acessos",
    description: "Cadastro, status e perfis da equipe.",
    group: "Administração",
    icon: Users,
    component: Usuarios,
    roles: ROLES.administradores,
    showInNav: true,
    order: 70,
    helpKey: "usuarios",
    sensitive: true,
    backendPrefixes: ["/api/users"],
  },
  {
    key: "lixeira",
    path: "/lixeira",
    label: "Lixeira",
    description: "Restauração e descarte controlado.",
    group: "Administração",
    icon: Trash2,
    component: Lixeira,
    roles: ROLES.gestores,
    showInNav: true,
    order: 80,
    helpKey: "lixeira",
    sensitive: true,
    backendPrefixes: ["/api/trash"],
  },
  {
    key: "ajuda",
    path: "/ajuda",
    label: "Ajuda",
    description: "Central de ajuda e orientação contextual.",
    group: "Administração",
    icon: BookOpen,
    component: Ajuda,
    helpKey: "ajuda",
    status: "hidden",
    sensitive: false,
  },
  {
    key: "whatsapp",
    path: "/whatsapp",
    label: "WhatsApp",
    description: "Integração ainda incompleta; acesso direto oculto do menu.",
    group: "Gestão",
    icon: Bell,
    component: Whatsapp,
    status: "beta",
    showInNav: false,
    sensitive: true,
    backendPrefixes: ["/api/whatsapp", "/api/webhooks"],
  },
];

export const LEGACY_REDIRECTS: LegacyRedirect[] = [
  {
    from: "/honorarios",
    to: "/financeiro?tab=honorarios",
    reason: "Honorários foi incorporado ao workspace financeiro.",
  },
  {
    from: "/sociedade",
    to: "/financeiro?tab=societaria",
    reason: "Gestão societária foi incorporada ao workspace financeiro.",
  },
  {
    from: "/office-contracts",
    to: "/financeiro?tab=contratos",
    reason: "Contratos do escritório foram incorporados ao financeiro.",
  },
  {
    from: "/partner-withdrawals",
    to: "/financeiro?tab=societaria&sub=saques",
    reason: "Saques de sócios foram consolidados na gestão societária.",
  },
  {
    from: "/financeiro-dashboard",
    to: "/financeiro",
    reason: "Dashboard financeiro foi incorporado ao workspace financeiro.",
  },
  {
    from: "/despesas",
    to: "/financeiro?tab=despesas",
    reason: "Despesas foram incorporadas ao workspace financeiro.",
  },
  {
    from: "/despesas-recorrentes",
    to: "/financeiro?tab=recorrentes",
    reason: "Despesas recorrentes foram incorporadas ao workspace financeiro.",
  },
  {
    from: "/agenda",
    to: "/atividades?view=calendario",
    reason: "Agenda foi incorporada à Central de Atividades.",
  },
  {
    from: "/kanban",
    to: "/atividades?view=kanban",
    reason: "Kanban de atividades foi incorporado à Central de Atividades.",
  },
  {
    from: "/assistente-ia",
    to: "/inteligencia?tab=assistente",
    reason: "Assistente foi incorporado ao workspace de Inteligência Jurídica.",
  },
  {
    from: "/ia",
    to: "/inteligencia?tab=ia",
    reason:
      "IA Jurídica foi incorporada ao workspace de Inteligência Jurídica.",
  },
  {
    from: "/ferramentas-ia",
    to: "/inteligencia?tab=ferramentas",
    reason:
      "Ferramentas de IA foram incorporadas ao workspace de Inteligência Jurídica.",
  },
  {
    from: "/jurimetria",
    to: "/inteligencia?tab=jurimetria",
    reason: "Jurimetria foi incorporada ao workspace de Inteligência Jurídica.",
  },
  {
    from: "/ia-saude",
    to: "/inteligencia?tab=saude",
    reason:
      "Saúde da IA foi incorporada ao workspace de Inteligência Jurídica.",
  },
  {
    from: "/conteudo-juridico",
    to: "/inteligencia?tab=conteudo",
    reason:
      "Conteúdo jurídico foi incorporado ao workspace de Inteligência Jurídica.",
  },
  {
    from: "/victory-vault",
    to: "/knowledge-hub",
    reason: "Victory Vault foi absorvido pelo Conhecimento Jurídico.",
  },
  {
    from: "/data-room",
    to: "/documentos?tab=dataroom",
    reason: "Data Room foi incorporado à Gestão Documental.",
  },
  {
    from: "/ambiental",
    to: "/ramos/ambiental",
    reason: "O núcleo ambiental foi incorporado aos Ramos do Direito.",
  },
  {
    from: "/dashboard-executivo",
    to: "/",
    reason: "O dashboard executivo é a tela inicial.",
  },
  {
    from: "/preferencias",
    to: "/configuracoes?tab=pessoal",
    reason: "Preferências pessoais ficam no workspace de configurações.",
  },
];

function routeBase(path: string): string {
  const dynamicIndex = path.indexOf("/:");
  return dynamicIndex >= 0 ? path.slice(0, dynamicIndex) : path;
}

export function getNavigationModules(role?: string | null): ModuleRoute[] {
  const groupIndex = new Map<string, number>(
    MODULE_GROUP_ORDER.map((group, index) => [group, index]),
  );

  return STAFF_ROUTES.filter((module) => {
    if (!module.showInNav) return false;
    if (module.status === "hidden" || module.status === "legacy") return false;
    if (!module.roles) return true;
    return Boolean(role && module.roles.includes(role));
  }).sort((a, b) => {
    const groupDiff =
      (groupIndex.get(a.group) ?? Number.MAX_SAFE_INTEGER) -
      (groupIndex.get(b.group) ?? Number.MAX_SAFE_INTEGER);
    if (groupDiff !== 0) return groupDiff;
    return (a.order ?? 999) - (b.order ?? 999);
  });
}

export function getHelpModuleKey(pathname: string): string | null {
  const candidates = STAFF_ROUTES.filter((module) => module.helpKey).sort(
    (a, b) => routeBase(b.path).length - routeBase(a.path).length,
  );
  const match = candidates.find((module) => {
    const base = routeBase(module.path);
    if (base === "/") return pathname === "/";
    return pathname === base || pathname.startsWith(`${base}/`);
  });
  return match?.helpKey ?? null;
}

export function canRoleAccessPath(
  role: string | undefined,
  route: string,
): boolean {
  const pathname = route.split("?")[0] || "/";
  const module = STAFF_ROUTES.find((item) => item.path === pathname);
  if (!module?.roles) return Boolean(module);
  return Boolean(role && module.roles.includes(role));
}

export function getModuleCatalog() {
  return STAFF_ROUTES.map(
    ({ component: _component, icon: _icon, ...module }) => module,
  );
}
