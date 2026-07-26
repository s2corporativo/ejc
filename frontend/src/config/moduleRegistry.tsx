import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import {
  BarChart3,
  Bell,
  BookOpen,
  Bot,
  Briefcase,
  CalendarClock,
  ClipboardPen,
  FileSignature,
  FileText,
  Filter,
  FolderOpen,
  Gavel,
  GitBranch,
  HeartPulse,
  LayoutDashboard,
  LayoutGrid,
  ListChecks,
  Newspaper,
  Plus,
  Scale,
  ScanSearch,
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
import { LEGACY_CANONICAL_REDIRECTS } from "./canonicalRoutes";

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
  // Espelha a matriz `_CLIENTES` do backend (routers/clients.py): gestão e
  // consulta de clientes. financeiro/estagiario/advogado_auxiliar recebem 403.
  clientes: ["superadmin", "admin", "socio", "advogado", "secretaria"],
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
  // Modo Essencial: marca os 7 destinos do dia a dia do advogado que ficam
  // sempre visíveis no topo da barra lateral (campo aditivo — não altera
  // rota/RBAC nem a ordenação de getNavigationModules).
  essential?: boolean;
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
const CadastroManual = lazy(() => import("../pages/CadastroManual"));
const DossieCliente = lazy(() => import("../pages/DossieCliente"));
const Casos = lazy(() => import("../pages/Casos"));
const CasoDetalhe = lazy(() => import("../pages/CasoDetalhe"));
const RaioXProcesso = lazy(() => import("../pages/RaioXProcesso"));
const SalaJuridica = lazy(() => import("../pages/SalaJuridica"));
const EntrevistaInteligente = lazy(
  () => import("../pages/EntrevistaInteligente"),
);
// PODA 2026-07 (simplificação de navegação): Prazos, Tarefas, Intimacoes e
// Suspensoes deixaram de ser roteados e os arquivos de página foram
// removidos (estavam órfãos, sem outro importador) — a funcionalidade está
// 100% coberta pela Central de Atividades (/atividades?tipo=prazo|tarefa|
// intimacao|suspensao). Ver LEGACY_REDIRECTS para os aliases /legado/*.
const Central = lazy(() => import("../pages/Central"));
const GestaoDocumental = lazy(() => import("../pages/GestaoDocumental"));
const Pecas = lazy(() => import("../pages/Pecas"));
const RamosHub = lazy(() => import("../pages/RamosHub"));
const RamoBase = lazy(() => import("../pages/ramos/RamoBase"));
const CRMLeads = lazy(() => import("../pages/CRMLeads"));
const FinanceiroWorkspace = lazy(() => import("../pages/FinanceiroWorkspace"));
const InteligenciaWorkspace = lazy(
  () => import("../pages/InteligenciaWorkspace"),
);
const GovernancaIA = lazy(() => import("../pages/GovernancaIA"));
// CONSOLIDAÇÃO CONHECIMENTO 2026-07: as superfícies KnowledgeHub, Biblioteca,
// MemoriaInstitucional e Wiki foram unificadas na aba canônica
// "Conhecimento" da Inteligência (/inteligencia?tab=conhecimento). As rotas
// viraram LEGACY_REDIRECTS; os arquivos de página seguem no repositório para
// rollback/histórico, mas não são mais roteados.
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
const CentralDiagnostico = lazy(() => import("../pages/CentralDiagnostico"));
const JornadaCaso = lazy(() => import("../pages/JornadaCaso"));
const Ferramentas = lazy(() => import("../pages/Ferramentas"));

// DECISÃO (EJC Command Center): a navegação é agrupada por INTENÇÃO em 4
// grupos — "Trabalhar um caso", "Pesquisar & IA", "Gerir o escritório" e
// "Administrar" — orientados às perguntas "em qual caso estou trabalhando?",
// "preciso pesquisar/gerar com IA?", "como vai a gestão do escritório?" e
// "o que preciso administrar?". Nenhum path/rota/role/essential foi alterado —
// apenas o agrupamento visual da barra lateral (usuários têm rotas salvas e o
// backend permanece a fonte de verdade de RBAC).
export const MODULE_GROUP_ORDER = [
  "Trabalhar um caso",
  "Pesquisar & IA",
  "Gerir o escritório",
  "Administrar",
] as const;

export const STAFF_ROUTES: ModuleRoute[] = [
  {
    key: "dashboard",
    path: "/",
    label: "Início",
    description: "Prioridades, agenda e casos recentes do seu dia.",
    group: "Trabalhar um caso",
    icon: LayoutDashboard,
    component: Dashboard,
    showInNav: true,
    essential: true,
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
    group: "Trabalhar um caso",
    icon: Plus,
    component: Casos,
    // Abertura de caso cria/seleciona cliente (POST /clients → matriz
    // _CLIENTES) e busca /users; perfis fora dessa matriz recebem 403.
    roles: ROLES.clientes,
    // A rota continua ativa, protegida e acessível pelo cabeçalho, Dashboard
    // e busca global. Não aparece no menu para evitar três entradas visuais
    // para a mesma tarefa.
    showInNav: false,
    essential: false,
    order: 10,
    helpKey: "casos",
    sensitive: true,
    backendPrefixes: ["/api/cases", "/api/clients"],
  },
  // CONSOLIDAÇÃO 2026-07: /central-relacionamento virou aba da Central
  // (/atividades?tab=relacionamento) — ver LEGACY_REDIRECTS.
  {
    key: "crm",
    path: "/crm-leads",
    label: "Funil de Leads",
    description: "Captação, qualificação e conversão de leads.",
    group: "Gerir o escritório",
    icon: Users,
    component: CRMLeads,
    helpKey: "crm",
    status: "hidden",
    sensitive: true,
    backendPrefixes: ["/api/clients"],
  },
  {
    key: "clientes",
    path: "/clientes",
    label: "Clientes",
    description: "Cadastro central de clientes e responsáveis.",
    // Cliente integra a entrada e o acompanhamento do caso; no Modo
    // Essencial deve vir antes de Documentos e Peças.
    group: "Trabalhar um caso",
    icon: Briefcase,
    component: Clientes,
    // Backend /clients (matriz _CLIENTES) nega financeiro/estagiario/auxiliar.
    roles: ROLES.clientes,
    showInNav: true,
    essential: true,
    order: 40,
    helpKey: "clientes",
    sensitive: true,
    backendPrefixes: ["/api/clients", "/api/clients/{client_id}/dossie"],
  },
  {
    key: "cadastro-manual",
    path: "/cadastro-manual",
    label: "Cadastro Manual",
    description:
      "Cadastro de clientes e abertura de casos sem IA, com fila offline.",
    group: "Trabalhar um caso",
    icon: ClipboardPen,
    component: CadastroManual,
    // Mesma matriz do backend /clients (_CLIENTES) — subconjunto seguro dos
    // papéis aceitos por POST /cases (secretaria/advogado/socio/admin).
    roles: ROLES.clientes,
    // Fora do menu para respeitar o guard "menu enxuto" de
    // moduleRegistry.test.ts: rota ativa via URL /cadastro-manual, Paleta de
    // Comandos e o atalho no hub de Áreas de Atuação (RamosHub), no padrão
    // das demais rotas podadas.
    showInNav: false,
    essential: false,
    order: 45,
    helpKey: "clientes",
    sensitive: true,
    usesAI: false,
    backendPrefixes: ["/api/clients", "/api/cases"],
  },
  {
    key: "cliente-detalhe",
    path: "/clientes/:clientId",
    label: "Dossiê do Cliente",
    description: "Detalhes e histórico do cliente.",
    group: "Gerir o escritório",
    icon: Briefcase,
    component: DossieCliente,
    helpKey: "clientes",
    status: "hidden",
    sensitive: true,
  },
  {
    key: "sala-juridica",
    path: "/sala-juridica",
    label: "Assistente Jurídico (IA)",
    description:
      "Porta de entrada conversacional: área de trabalho livre, chat jurídico com estado probatório e conversão controlada em caso.",
    group: "Pesquisar & IA",
    icon: Sparkles,
    component: SalaJuridica,
    roles: ROLES.juridico,
    showInNav: true,
    essential: true,
    order: 5,
    helpKey: "inteligencia",
    usesAI: true,
    sensitive: true,
    backendPrefixes: ["/api/sala-juridica", "/api/ai"],
  },
  {
    key: "raio-x-processo",
    path: "/raio-x",
    label: "Triagem e Raio-X",
    description:
      "Análise preliminar autônoma de documentos antes da abertura de um caso.",
    group: "Pesquisar & IA",
    icon: ScanSearch,
    component: RaioXProcesso,
    roles: ROLES.juridico,
    showInNav: true,
    essential: false,
    order: 15,
    helpKey: "inteligencia",
    usesAI: true,
    sensitive: true,
    backendPrefixes: ["/api/raio-x", "/api/documentos-ia", "/api/ai/skills"],
  },
  {
    key: "casos",
    path: "/casos",
    label: "Casos",
    description: "Gestão jurídica central de casos e processos.",
    group: "Trabalhar um caso",
    icon: Gavel,
    component: Casos,
    showInNav: true,
    essential: true,
    order: 20,
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
    group: "Trabalhar um caso",
    icon: Gavel,
    component: CasoDetalhe,
    helpKey: "casos",
    status: "hidden",
    sensitive: true,
  },
  // Rota-detalhe (padrão /casos/:id): jornada guiada das 9 etapas do caso.
  // status hidden = fora do menu, igual a caso-detalhe.
  {
    key: "caso-jornada",
    path: "/casos/:id/jornada",
    label: "Jornada do Caso",
    description:
      "Linha de etapas do caso, da entrada do cliente à gestão contínua.",
    group: "Trabalhar um caso",
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
    group: "Trabalhar um caso",
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
    key: "ramos",
    path: "/areas-de-atuacao",
    label: "Áreas de Atuação",
    description: "Áreas jurídicas e ferramentas especializadas do escritório.",
    group: "Pesquisar & IA",
    icon: Scale,
    component: RamosHub,
    // Ferramentas dos ramos exigem a equipe jurídica (_EQUIPE no backend);
    // financeiro/secretaria recebem 403 ao acionar qualquer ferramenta.
    roles: ROLES.juridico,
    showInNav: true,
    order: 30,
    helpKey: "ramos",
    usesAI: true,
    sensitive: true,
  },
  {
    key: "ramo-detalhe",
    path: "/areas-de-atuacao/:slug",
    label: "Núcleo Jurídico",
    description: "Ferramentas especializadas do ramo selecionado.",
    group: "Pesquisar & IA",
    icon: Scale,
    component: RamoBase,
    helpKey: "ramos",
    status: "hidden",
    usesAI: true,
    sensitive: true,
  },
  // Central unificada: atividades (agenda/prazos/tarefas/intimações) +
  // relacionamento (funil, captação e contato) em abas na mesma rota.
  {
    key: "atividades",
    path: "/atividades",
    label: "Agenda e Prazos",
    description:
      "Agenda, prazos, tarefas e intimações + relacionamento com clientes em abas.",
    group: "Trabalhar um caso",
    icon: CalendarClock,
    component: Central,
    showInNav: true,
    essential: true,
    order: 30,
    helpKey: "atividades",
    sensitive: true,
    backendPrefixes: [
      "/api/atividades",
      "/api/agenda-eventos",
      "/api/analytics",
      "/api/clients",
      "/api/notifications",
    ],
  },
  {
    key: "documentos",
    path: "/documentos",
    label: "Documentos",
    description: "Gestão documental e compartilhamento controlado.",
    group: "Trabalhar um caso",
    icon: FolderOpen,
    component: GestaoDocumental,
    showInNav: true,
    essential: true,
    order: 60,
    helpKey: "documentos",
    sensitive: true,
    usesAI: true,
    backendPrefixes: [
      "/api/documents",
      "/api/data-rooms",
      "/api/documentos-ia",
    ],
  },
  {
    key: "pecas",
    path: "/pecas",
    label: "Peças",
    description: "Produção, validação, revisão e aprovação de peças.",
    group: "Trabalhar um caso",
    icon: FileText,
    component: Pecas,
    showInNav: true,
    essential: true,
    order: 70,
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
    group: "Trabalhar um caso",
    icon: FileSignature,
    component: Assinaturas,
    // PODA 2026-07: fluxo de apoio à produção; acessível pelos atalhos do
    // Dashboard e pela paleta ⌘K. Rota ativa.
    status: "hidden",
    helpKey: "assinaturas",
    sensitive: true,
    backendPrefixes: ["/api/signatures"],
  },
  {
    key: "workflow",
    path: "/workflow",
    label: "Workflows",
    description: "Fluxos, etapas e SLAs por área jurídica.",
    group: "Trabalhar um caso",
    icon: GitBranch,
    component: Workflow,
    // PODA 2026-07: configuração de fluxos usada esporadicamente; atalho no
    // Dashboard. Rota ativa.
    status: "hidden",
    helpKey: "workflow",
    sensitive: true,
    backendPrefixes: ["/api/workflow"],
  },
  {
    key: "checklists",
    path: "/checklists",
    label: "Checklists",
    description: "Listas de verificação vinculadas à produção.",
    group: "Trabalhar um caso",
    icon: ListChecks,
    component: Checklists,
    // PODA 2026-07: apoio à produção, alcançável pelo caso e atalhos do
    // Dashboard. Rota ativa.
    status: "hidden",
    helpKey: "checklists",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/checklists"],
  },
  {
    key: "inteligencia",
    path: "/inteligencia",
    label: "Pesquisa e IA",
    description:
      "Pesquisa jurídica com IA: agentes, análise, jurimetria e conhecimento.",
    group: "Pesquisar & IA",
    icon: Sparkles,
    component: InteligenciaWorkspace,
    roles: ROLES.juridico,
    showInNav: true,
    essential: true,
    order: 10,
    helpKey: "inteligencia",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/ai", "/api/ai/core", "/api/ai/skills"],
  },
  {
    key: "prompts",
    path: "/prompts",
    label: "Prompts Operacionais",
    description: "Modelos de instrução reutilizáveis pela equipe.",
    group: "Pesquisar & IA",
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
    group: "Pesquisar & IA",
    icon: Scale,
    component: DataJudBusca,
    // PODA 2026-07: consulta pontual, acessível pelos atalhos do Dashboard
    // e de dentro do caso. Rota ativa.
    status: "hidden",
    helpKey: "datajud",
    sensitive: true,
    backendPrefixes: ["/api/v1/datajud"],
  },
  {
    key: "diario-oficial",
    path: "/diario-oficial",
    label: "Diário Oficial",
    description: "Palavras-chave, publicações e alertas monitorados.",
    group: "Pesquisar & IA",
    icon: ScrollText,
    component: DiarioOficial,
    // PODA 2026-07: monitoramento alcançável pelo Radar Regulatório e
    // atalhos do Dashboard. Rota ativa.
    status: "hidden",
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
    group: "Pesquisar & IA",
    icon: Bell,
    component: RadarRegulatorio,
    // PODA 2026-07: radar consultivo; atalho no Dashboard. Rota ativa.
    status: "hidden",
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
    group: "Pesquisar & IA",
    icon: ShieldAlert,
    component: RadarCompliance,
    roles: ROLES.compliance,
    // PODA 2026-07: radar consultivo; atalho no Dashboard. Rota ativa.
    status: "hidden",
    helpKey: "compliance",
    sensitive: true,
    usesAI: true,
  },
  {
    key: "noticias",
    path: "/noticias",
    label: "Notícias Jurídicas",
    description: "Atualizações e conteúdo jurídico externo.",
    group: "Pesquisar & IA",
    icon: Newspaper,
    component: Noticias,
    // PODA 2026-07: o card de notícias do Dashboard cobre o uso diário;
    // página completa segue por atalho/URL. Rota ativa.
    status: "hidden",
    helpKey: "noticias",
    sensitive: false,
  },
  {
    key: "financeiro",
    path: "/financeiro",
    label: "Financeiro e Sociedade",
    description: "Honorários, despesas, NFS-e, contratos e gestão societária.",
    group: "Gerir o escritório",
    icon: Wallet,
    component: FinanceiroWorkspace,
    roles: ROLES.financeiro,
    showInNav: true,
    essential: true,
    order: 10,
    helpKey: "financeiro",
    sensitive: true,
    backendPrefixes: [
      "/api/financeiro",
      "/api/fees",
      "/api/v1/despesas",
      "/api/nfse",
    ],
  },
  {
    key: "produtividade",
    path: "/produtividade",
    label: "Produtividade",
    description: "Indicadores operacionais da equipe.",
    group: "Gerir o escritório",
    icon: BarChart3,
    component: Produtividade,
    // PODA 2026-07: indicadores gerenciais; atalho no bloco administrativo
    // do Dashboard. Rota ativa.
    status: "hidden",
    helpKey: "produtividade",
    sensitive: true,
  },
  {
    key: "configuracoes",
    path: "/configuracoes",
    label: "Preferências",
    description: "Aparência, navegação, segurança e preferências pessoais.",
    group: "Administrar",
    icon: Settings,
    component: Configuracoes,
    showInNav: true,
    order: 10,
    helpKey: "configuracoes",
    sensitive: false,
  },
  {
    key: "governanca-ia",
    path: "/ia-governanca",
    label: "Governança da IA",
    description: "Curadoria, fontes e regras de segurança da IA.",
    group: "Administrar",
    icon: Sparkles,
    component: GovernancaIA,
    roles: ROLES.gestores,
    // PODA 2026-07: painel de governança usado por gestores; atalho no
    // bloco administrativo do Dashboard. Rota ativa.
    status: "hidden",
    helpKey: "governanca-ia",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/ia-governanca"],
  },
  {
    key: "central-diagnostico",
    path: "/diagnostico",
    label: "Central de Diagnóstico",
    description: "Saúde dos subsistemas do EJC em tempo real.",
    group: "Administrar",
    icon: HeartPulse,
    component: CentralDiagnostico,
    roles: ROLES.gestores,
    showInNav: true,
    order: 20,
    helpKey: "autofix",
    sensitive: true,
    backendPrefixes: ["/api/diagnostico"],
  },
  {
    key: "auditoria",
    path: "/auditoria",
    label: "Auditoria",
    description: "Trilha imutável de ações críticas.",
    group: "Administrar",
    icon: ShieldCheck,
    component: Auditoria,
    roles: ROLES.gestores,
    // PODA 2026-07: trilha consultada sob demanda; atalho no bloco
    // administrativo do Dashboard. Rota ativa.
    status: "hidden",
    helpKey: "auditoria",
    sensitive: true,
    backendPrefixes: ["/api/audit"],
  },
  {
    key: "mapa-modulos",
    path: "/mapa-modulos",
    label: "Mapa de Módulos",
    description: "Inventário técnico e funcional do EJC.",
    group: "Administrar",
    icon: LayoutGrid,
    component: MapaModulos,
    roles: ROLES.gestores,
    helpKey: "autofix",
    sensitive: false,
    // PODA 2026-07: inventário técnico (beta); atalho no bloco
    // administrativo do Dashboard. Rota ativa.
    status: "hidden",
    backendPrefixes: ["/api/system-modules"],
  },
  {
    key: "usuarios",
    path: "/usuarios",
    label: "Usuários e Acessos",
    description: "Cadastro, status e perfis da equipe.",
    group: "Administrar",
    icon: Users,
    component: Usuarios,
    roles: ROLES.administradores,
    showInNav: true,
    order: 10,
    helpKey: "usuarios",
    sensitive: true,
    backendPrefixes: ["/api/users"],
  },
  {
    key: "lixeira",
    path: "/lixeira",
    label: "Lixeira",
    description: "Restauração e descarte controlado.",
    group: "Administrar",
    icon: Trash2,
    component: Lixeira,
    roles: ROLES.gestores,
    // PODA 2026-07: restauração eventual; atalho no bloco administrativo
    // do Dashboard. Rota ativa.
    status: "hidden",
    helpKey: "lixeira",
    sensitive: true,
    backendPrefixes: ["/api/trash"],
  },
  {
    key: "ajuda",
    path: "/ajuda",
    label: "Ajuda",
    description: "Central de ajuda e orientação contextual.",
    group: "Administrar",
    icon: BookOpen,
    component: Ajuda,
    helpKey: "ajuda",
    status: "hidden",
    sensitive: false,
  },
  // PODA 2026-07: hub de descoberta para os módulos reais que ficaram fora
  // do menu principal — evita reabrir 18 itens na barra lateral.
  {
    key: "ferramentas",
    path: "/ferramentas",
    label: "Mais Ferramentas",
    description:
      "Catálogo dos módulos avançados que não ficam no menu principal.",
    group: "Administrar",
    icon: LayoutGrid,
    component: Ferramentas,
    showInNav: true,
    order: 90,
    helpKey: "ferramentas",
    sensitive: false,
  },
];

export const LEGACY_REDIRECTS: LegacyRedirect[] = [
  ...LEGACY_CANONICAL_REDIRECTS,
  // PODA 2026-07: /legado/prazos, /legado/tarefas, /legado/intimacoes e
  // /legado/suspensoes deixaram de ser rotas roteáveis (ver comentário acima
  // de `const Central`); os aliases curtos /prazos, /tarefas, /intimacoes e
  // /suspensoes já existiam via LEGACY_CANONICAL_REDIRECTS — estes cobrem
  // links/favoritos que ainda apontem para o caminho /legado/*.
  {
    from: "/legado/prazos",
    to: "/atividades?tipo=prazo",
    reason: "Prazos foram consolidados na Central de Agenda e Prazos.",
  },
  {
    from: "/legado/tarefas",
    to: "/atividades?tipo=tarefa",
    reason: "Tarefas foram consolidadas na Central de Agenda e Prazos.",
  },
  {
    from: "/legado/intimacoes",
    to: "/atividades?tipo=intimacao",
    reason: "Intimações foram consolidadas na Central de Agenda e Prazos.",
  },
  {
    from: "/legado/suspensoes",
    to: "/atividades?tipo=suspensao",
    reason: "Suspensões foram consolidadas na Central de Agenda e Prazos.",
  },
  {
    from: "/sala-analise",
    to: "/raio-x",
    reason:
      "A Sala de Análise foi absorvida pelo Raio-X (mesmo backend); a nova porta de entrada conversacional é a Sala Jurídica.",
  },
  {
    from: "/central-relacionamento",
    to: "/atividades?tab=relacionamento",
    reason: "Central de Relacionamento virou aba da Central unificada.",
  },
  {
    from: "/dashboard",
    to: "/",
    reason: "O dashboard unificado é a tela inicial.",
  },
  {
    from: "/honorarios",
    to: "/financeiro?tab=honorarios",
    reason: "Honorários foi incorporado ao workspace financeiro.",
  },
  {
    from: "/nfse",
    to: "/financeiro?tab=nfse",
    reason: "NFS-e vive como aba do workspace financeiro.",
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
    to: "/inteligencia?tab=conhecimento",
    reason: "Victory Vault foi absorvido pelo Conhecimento Jurídico.",
  },
  {
    from: "/data-room",
    to: "/documentos?tab=dataroom",
    reason: "Data Room foi incorporado à Gestão Documental.",
  },
  {
    from: "/ambiental",
    to: "/areas-de-atuacao/ambiental",
    reason: "O núcleo ambiental foi incorporado às Áreas de Atuação.",
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
  {
    from: "/administracao/configuracoes",
    to: "/configuracoes?tab=administracao",
    reason: "Administração do EJC virou uma aba do workspace de configurações.",
  },
  {
    from: "/conhecimento",
    to: "/inteligencia?tab=conhecimento",
    reason:
      "Curadoria da base de conhecimento foi incorporada ao workspace de Inteligência Jurídica.",
  },
  // CONSOLIDAÇÃO CONHECIMENTO 2026-07: as quatro superfícies redundantes
  // (Conhecimento Jurídico/KnowledgeHub, Biblioteca, Memória Institucional e
  // Wiki) foram unificadas na aba canônica "Conhecimento" da Inteligência.
  {
    from: "/legado/knowledge-hub",
    to: "/inteligencia?tab=conhecimento",
    reason:
      "Conhecimento Jurídico (KnowledgeHub) foi unificado na aba Conhecimento da Inteligência.",
  },
  {
    from: "/biblioteca",
    to: "/inteligencia?tab=conhecimento",
    reason:
      "Biblioteca Jurídica foi unificada na aba Conhecimento da Inteligência.",
  },
  {
    from: "/memoria",
    to: "/inteligencia?tab=conhecimento",
    reason:
      "Memória Institucional foi unificada na aba Conhecimento da Inteligência.",
  },
  {
    from: "/wiki",
    to: "/inteligencia?tab=conhecimento",
    reason: "Wiki foi unificada na aba Conhecimento da Inteligência.",
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

/**
 * Título humano do módulo a partir do helpKey (ex.: "inteligencia" →
 * "Inteligência Jurídica"). Evita exibir o slug técnico em títulos de UI
 * como o painel "Ajuda — {módulo}".
 */
export function getModuleTitleByHelpKey(helpKey: string): string | null {
  const match = STAFF_ROUTES.find((module) => module.helpKey === helpKey);
  return match?.label ?? null;
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
