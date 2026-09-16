import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import {
  BarChart3,
  Bell,
  BookOpen,
  Bot,
  Briefcase,
  BriefcaseBusiness,
  CalendarClock,
  ClipboardPen,
  FileSignature,
  FileText,
  Filter,
  FolderOpen,
  Gavel,
  GitBranch,
  HeartPulse,
  Inbox,
  LayoutDashboard,
  LayoutGrid,
  ListChecks,
  Plus,
  Library,
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
  // Modo Essencial: marca os destinos do dia a dia que ficam sempre visíveis
  // no topo da barra lateral. O backend continua a fonte de verdade do RBAC.
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
const Dpt360Workspace = lazy(() => import("../pages/dpt360/Dpt360Workspace"));
const Clientes = lazy(() => import("../pages/Clientes"));
const CadastroManual = lazy(() => import("../pages/CadastroManual"));
const DossieCliente = lazy(() => import("../pages/DossieCliente"));
const Casos = lazy(() => import("../pages/Casos"));
const CasoDetalhe = lazy(() => import("../pages/CasoDetalhe"));
const RaioXProcesso = lazy(() => import("../pages/RaioXProcesso"));
const Ajuizamento = lazy(() => import("../pages/Ajuizamento"));
const AjuizamentoPerfis = lazy(() => import("../pages/AjuizamentoPerfis"));
const SalaJuridica = lazy(() => import("../pages/SalaJuridica"));
const EntrevistaInteligente = lazy(
  () => import("../pages/EntrevistaInteligente"),
);
const Central = lazy(() => import("../pages/Central"));
const AgendaDia = lazy(() => import("../pages/AgendaDia"));
const GestaoDocumental = lazy(() => import("../pages/GestaoDocumental"));
const Pecas = lazy(() => import("../pages/Pecas"));
const RamosHub = lazy(() => import("../pages/RamosHub"));
const RamoBase = lazy(() => import("../pages/ramos/RamoBase"));
const CRMLeads = lazy(() => import("../pages/CRMLeads"));
const FinanceiroWorkspace = lazy(() => import("../pages/FinanceiroWorkspace"));
const SociedadeWorkspace = lazy(() => import("../pages/SociedadeWorkspace"));
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
// Onda 2: as duas telas de radar viraram MODOS de uma só (pages/Radar.tsx).
// Os componentes originais seguem no repositório — a casca os renderiza
// embutidos, e as rotas antigas viram LEGACY_REDIRECTS.
const Radar = lazy(() => import("../pages/Radar"));
const Checklists = lazy(() => import("../pages/Checklists"));
const Workflow = lazy(() => import("../pages/Workflow"));
const Assinaturas = lazy(() => import("../pages/Assinaturas"));
const Prompts = lazy(() => import("../pages/Prompts"));
const BancoTeses = lazy(() => import("../pages/BancoTeses"));
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
const EntradaUnica = lazy(() => import("../pages/EntradaUnica"));

// EJC Command Center: navegação agrupada por intenção. "Mais" é catálogo de
// capacidades avançadas e deixa de ser semanticamente uma tela administrativa.
export const MODULE_GROUP_ORDER = [
  "Trabalhar um caso",
  "Pesquisar & IA",
  "Gerir o escritório",
  "Administrar",
  "Mais",
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
  {
    key: "dpt360",
    path: "/dpt360",
    label: "DPT Empresarial 360",
    description:
      "Cockpit de inteligência, prevenção e gestão jurídica empresarial.",
    group: "Pesquisar & IA",
    icon: BriefcaseBusiness,
    component: Dpt360Workspace,
    roles: ROLES.compliance,
    showInNav: true,
    essential: true,
    order: 1,
    helpKey: "dpt360",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/clients", "/api/cases", "/api/deadlines"],
  },
  {
    key: "dpt360-subroutes", // gitleaks:allow -- chave semântica do registry, não credencial
    path: "/dpt360/*",
    label: "DPT Empresarial 360",
    description: "Navegação interna do workspace empresarial.",
    group: "Pesquisar & IA",
    icon: BriefcaseBusiness,
    component: Dpt360Workspace,
    roles: ROLES.compliance,
    showInNav: false,
    status: "hidden",
    helpKey: "dpt360",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/clients", "/api/cases", "/api/deadlines"],
  },
  {
    key: "dpt360-company-detail",
    path: "/dpt360/empresas/:clientId",
    label: "Empresa 360",
    description: "Visão jurídica empresarial do cliente pessoa jurídica.",
    group: "Pesquisar & IA",
    icon: BriefcaseBusiness,
    component: Dpt360Workspace,
    roles: ROLES.compliance,
    showInNav: false,
    status: "hidden",
    helpKey: "dpt360",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/clients", "/api/cases", "/api/deadlines"],
  },
  {
    key: "entrada",
    path: "/entrada",
    label: "Entrada Jurídica",
    description:
      "Porta única para abrir casos: análise assistida ou cadastro manual no mesmo fluxo.",
    group: "Trabalhar um caso",
    icon: Inbox,
    component: EntradaUnica,
    // A rota recebe os perfis que podem criar/selecionar cliente. Dentro da
    // própria página, o modo IA fica restrito a advogado+; secretaria cai no
    // modo manual. Backend continua autoritativo para cada POST.
    roles: ROLES.clientes,
    showInNav: true,
    essential: true,
    order: 15,
    helpKey: "casos",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/entrada", "/api/entrada-universal", "/api/clients"],
  },
  // Compatibilidade: /casos/novo continua ativo para links históricos, mas não
  // deve ser anunciado como outra porta de entrada.
  {
    key: "caso-novo",
    path: "/casos/novo",
    label: "Novo Caso",
    description:
      "Compatibilidade da abertura guiada histórica; novos atalhos usam Entrada Jurídica.",
    group: "Trabalhar um caso",
    icon: Plus,
    component: Casos,
    roles: ROLES.clientes,
    showInNav: false,
    essential: false,
    order: 10,
    helpKey: "casos",
    sensitive: true,
    backendPrefixes: ["/api/cases", "/api/clients"],
  },
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
    group: "Trabalhar um caso",
    icon: Briefcase,
    component: Clientes,
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
    roles: ROLES.clientes,
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
    // Defesa em profundidade: espelha a mesma matriz da listagem e do backend.
    roles: ROLES.clientes,
    helpKey: "clientes",
    status: "hidden",
    sensitive: true,
  },
  {
    key: "sala-juridica",
    path: "/sala-juridica",
    label: "Sala Jurídica",
    description:
      "Área conversacional de trabalho jurídico com estado probatório e conversão controlada em caso.",
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
    label: "Raio-X de Documentos",
    description:
      "Análise preliminar autônoma de documentos (autos, contratos, provas) antes da abertura de um caso.",
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
  {
    key: "caso-jornada",
    path: "/casos/:id/jornada",
    label: "Jornada do Caso",
    description: "Adapter histórico para a Visão do Caso.",
    group: "Trabalhar um caso",
    icon: GitBranch,
    component: JornadaCaso,
    helpKey: "casos",
    status: "hidden",
    sensitive: true,
  },
  {
    key: "ajuizamento",
    path: "/ajuizamento",
    label: "Ajuizamento",
    description:
      "Do caso ao protocolo: validação, revisão humana, assinatura e registro do protocolo.",
    group: "Trabalhar um caso",
    icon: Gavel,
    component: Ajuizamento,
    roles: ROLES.juridico,
    showInNav: true,
    order: 25,
    helpKey: "casos",
    sensitive: true,
    backendPrefixes: ["/api/ajuizamento"],
  },
  {
    key: "ajuizamento-perfis",
    path: "/ajuizamento/perfis",
    label: "Perfis de tribunal",
    description:
      "Endpoint, versão, capacidades e homologação por tribunal (segredos só por referência).",
    group: "Administrar",
    icon: ShieldCheck,
    component: AjuizamentoPerfis,
    roles: ROLES.administradores,
    showInNav: false,
    status: "hidden",
    helpKey: "casos",
    sensitive: true,
    backendPrefixes: ["/api/ajuizamento/perfis"],
  },
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
    roles: ROLES.juridico,
    helpKey: "ramos",
    status: "hidden",
    usesAI: true,
    sensitive: true,
  },
  {
    key: "atividades",
    path: "/atividades",
    // Rótulo canônico da navegação (LayoutReference e CommandPalette consomem
    // este campo — não existe mais override de rótulo no shell).
    label: "Prazos e Agenda",
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
    key: "atividades-dia",
    path: "/atividades/dia/:date",
    label: "Agenda do Dia",
    description:
      "Atividades da data selecionada no calendário semanal do escritório.",
    group: "Trabalhar um caso",
    icon: CalendarClock,
    component: AgendaDia,
    status: "hidden",
    helpKey: "atividades",
    sensitive: true,
    backendPrefixes: ["/api/atividades", "/api/agenda-eventos"],
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
    description: "Fila global de produção, validação, revisão e protocolo.",
    group: "Trabalhar um caso",
    icon: FileText,
    component: Pecas,
    roles: ROLES.juridico,
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
    description: "Fila global de solicitações e trilha de assinatura.",
    group: "Trabalhar um caso",
    icon: FileSignature,
    component: Assinaturas,
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
    status: "hidden",
    helpKey: "checklists",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/checklists"],
  },
  {
    key: "inteligencia",
    path: "/inteligencia",
    // Rótulo canônico da navegação (fonte única — antes havia override no shell).
    label: "IA Jurídica",
    description:
      "Pesquisa jurídica, análise, jurimetria, conhecimento e precificação de honorários.",
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
    backendPrefixes: [
      "/api/ai",
      "/api/ai/core",
      "/api/ai/skills",
      "/api/honorarios-oab",
    ],
  },
  {
    key: "banco-teses",
    path: "/teses",
    label: "Banco de Teses",
    description:
      "Teses do escritório e em quais processos cada uma pode caber.",
    group: "Pesquisar & IA",
    icon: Library,
    component: BancoTeses,
    roles: ROLES.juridico,
    status: "beta",
    showInNav: true,
    backendPrefixes: ["/api/teses"],
    usesAI: false,
    sensitive: true,
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
    description: "Pesquisa processual global e sincronização de dados do CNJ.",
    group: "Pesquisar & IA",
    icon: Scale,
    component: DataJudBusca,
    status: "hidden",
    helpKey: "datajud",
    sensitive: true,
    backendPrefixes: ["/api/datajud"],
  },
  {
    key: "diario-oficial",
    path: "/diario-oficial",
    label: "Diário Oficial",
    description: "Palavras-chave, publicações e alertas monitorados.",
    group: "Pesquisar & IA",
    icon: ScrollText,
    component: DiarioOficial,
    status: "hidden",
    helpKey: "diario-oficial",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/diario-oficial"],
  },
  {
    key: "radar",
    path: "/radar",
    label: "Radar",
    description:
      "Alertas do Diário Oficial, do monitoramento regulatório e dos autos ambientais — por risco ou agregados no período.",
    group: "Pesquisar & IA",
    icon: ShieldAlert,
    component: Radar,
    roles: ROLES.compliance,
    status: "hidden",
    helpKey: "compliance",
    sensitive: true,
    usesAI: true,
    backendPrefixes: ["/api/compliance/radar", "/api/regulatorio"],
  },
  {
    key: "financeiro",
    path: "/financeiro",
    label: "Financeiro",
    description: "Recebimentos, despesas, NFS-e, contratos e caixa do escritório.",
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
      "/api/despesas",
      "/api/nfse",
    ],
  },
  {
    key: "sociedade",
    path: "/gestao-escritorio/sociedade",
    label: "Sociedade",
    description: "Sócios, participações, distribuições e retiradas.",
    group: "Gerir o escritório",
    icon: Users,
    component: SociedadeWorkspace,
    roles: ROLES.gestores,
    // 2026-09-05 (CORTE-5 reenquadrado): o módulo NÃO foi removido porque a
    // tabela partner_withdrawals é escrita por honorarios_oab.py e lida por
    // extratos.py — cortar quebraria o fluxo de honorários. Sai só do menu;
    // a rota segue viva (deep-link) até haver quadro societário cadastrado.
    showInNav: false,
    status: "hidden",
    essential: false,
    order: 20,
    helpKey: "financeiro",
    sensitive: true,
    backendPrefixes: ["/api/sociedade", "/api/partner-withdrawals"],
  },
  {
    key: "produtividade",
    path: "/produtividade",
    label: "Produtividade",
    description: "Indicadores operacionais da equipe.",
    group: "Gerir o escritório",
    icon: BarChart3,
    component: Produtividade,
    status: "hidden",
    helpKey: "produtividade",
    sensitive: true,
  },
  {
    key: "configuracoes",
    path: "/configuracoes",
    // Rótulo canônico da navegação (fonte única — antes havia override no shell).
    label: "Configurações",
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
    // Bloco 4 do plano de lançamento: fora do menu lateral (é administração,
    // não estação de trabalho). Alcançável por /diagnostico e pelo cartão em
    // Configurações → Administração. Rota e RBAC inalterados.
    showInNav: false,
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
    // Bloco 4: fora do menu lateral; Configurações → Administração já tinha o
    // cartão "Usuários e acessos". Rota e RBAC inalterados.
    showInNav: false,
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
  {
    key: "ferramentas",
    path: "/ferramentas",
    label: "Mais Ferramentas",
    description:
      "Catálogo de capacidades avançadas que não ficam no menu principal.",
    group: "Mais",
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
    from: "/compliance/radar",
    to: "/radar",
    reason:
      "Radar de Compliance e Radar Regulatório eram a mesma matéria em duas telas; viraram modos de /radar (feed é o padrão).",
  },
  {
    from: "/radar-regulatorio",
    to: "/radar?modo=digest",
    reason:
      "O radar regulatório é o DIGEST agregado do mesmo material — agora o modo `digest` de /radar.",
  },
  {
    from: "/dashboard",
    to: "/",
    reason: "O dashboard unificado é a tela inicial.",
  },
  {
    from: "/honorarios",
    to: "/financeiro?tab=honorarios",
    reason: "Honorários contratados e recebimentos vivem no workspace financeiro.",
  },
  {
    from: "/nfse",
    to: "/financeiro?tab=nfse",
    reason: "NFS-e vive como aba do workspace financeiro.",
  },
  {
    from: "/sociedade",
    to: "/gestao-escritorio/sociedade",
    reason: "Gestão societária foi separada do caixa operacional do escritório.",
  },
  {
    from: "/office-contracts",
    to: "/financeiro?tab=contratos",
    reason: "Contratos do escritório ficam disponíveis no menu Mais do Financeiro.",
  },
  {
    from: "/partner-withdrawals",
    to: "/gestao-escritorio/sociedade?sub=saques",
    reason: "Retiradas pertencem à gestão societária, separada do caixa operacional.",
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
    reason: "O deep-link histórico é preservado enquanto a recorrência migra para o formulário único de despesas.",
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
    from: "/legado/prazos",
    to: "/atividades?tipo=prazo",
    reason: "A tela legada de Prazos foi consolidada na Central de Atividades.",
  },
  {
    from: "/legado/tarefas",
    to: "/atividades?tipo=tarefa",
    reason:
      "A tela legada de Tarefas foi consolidada na Central de Atividades.",
  },
  {
    from: "/legado/intimacoes",
    to: "/atividades?tipo=intimacao",
    reason:
      "A tela legada de Intimações foi consolidada na Central de Atividades.",
  },
  {
    from: "/legado/suspensoes",
    to: "/atividades?tipo=suspensao",
    reason:
      "A tela legada de Suspensões foi consolidada na Central de Atividades.",
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
  {
    from: "/leads",
    to: "/crm-leads",
    reason: "O funil de leads vive no workspace CRM de leads.",
  },
  {
    from: "/raiox",
    to: "/raio-x",
    reason: "O Raio-X de documentos usa a rota canônica /raio-x.",
  },
  {
    from: "/diario",
    to: "/diario-oficial",
    reason: "O Diário Oficial usa a rota canônica /diario-oficial.",
  },
  {
    from: "/workflows",
    to: "/workflow",
    reason: "Workflows usa a rota canônica singular /workflow.",
  },
  {
    from: "/entrada-caso",
    to: "/entrada",
    reason: "A Entrada de Caso (avançada) vive na rota /entrada.",
  },
  {
    from: "/defesas",
    to: "/ferramentas",
    reason: "Defesas e Revisões é um painel dentro de Mais Ferramentas.",
  },
];

function routeBase(path: string): string {
  const dynamicIndex = path.indexOf("/:");
  return dynamicIndex >= 0 ? path.slice(0, dynamicIndex) : path;
}

/** Matcher mínimo compatível com os padrões registrados no EJC (:param e /*). */
export function routePatternMatches(
  pattern: string,
  pathname: string,
): boolean {
  if (pattern === pathname) return true;
  if (pattern.endsWith("/*")) {
    const base = pattern.slice(0, -2);
    return pathname === base || pathname.startsWith(`${base}/`);
  }
  const expected = pattern.split("/").filter(Boolean);
  const actual = pathname.split("/").filter(Boolean);
  if (expected.length !== actual.length) return false;
  return expected.every(
    (segment, index) => segment.startsWith(":") || segment === actual[index],
  );
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

export type NavigationGroup = {
  name: string;
  items: ModuleRoute[];
};

/**
 * Agrupa módulos JÁ ORDENADOS (getNavigationModules ordena por
 * MODULE_GROUP_ORDER + order) em blocos consecutivos para a sidebar renderizar
 * os cabeçalhos de grupo. Antes os grupos eram computados e nunca exibidos —
 * terceira fonte de verdade da navegação aposentada (auditoria Fase 4).
 */
export function groupNavigationModules(
  items: ModuleRoute[],
): NavigationGroup[] {
  const groups: NavigationGroup[] = [];
  for (const item of items) {
    const last = groups[groups.length - 1];
    if (last && last.name === item.group) {
      last.items.push(item);
    } else {
      groups.push({ name: item.group, items: [item] });
    }
  }
  return groups;
}

export function getHelpModuleKey(pathname: string): string | null {
  const candidates = STAFF_ROUTES.filter((module) => module.helpKey).sort(
    (a, b) => routeBase(b.path).length - routeBase(a.path).length,
  );
  const match = candidates.find((module) => {
    const base = routeBase(module.path);
    if (base === "/") return pathname === "/";
    if (module.path.includes(":"))
      return routePatternMatches(module.path, pathname);
    if (base.endsWith("/*")) {
      const wildcardBase = base.slice(0, -2);
      return (
        pathname === wildcardBase || pathname.startsWith(`${wildcardBase}/`)
      );
    }
    return pathname === base || pathname.startsWith(`${base}/`);
  });
  return match?.helpKey ?? null;
}

export function getModuleTitleByHelpKey(helpKey: string): string | null {
  const match = STAFF_ROUTES.find((module) => module.helpKey === helpKey);
  return match?.label ?? null;
}

export function canRoleAccessPath(
  role: string | undefined,
  route: string,
): boolean {
  const pathname = route.split("?")[0] || "/";
  const module = STAFF_ROUTES.find((item) =>
    routePatternMatches(item.path, pathname),
  );
  if (!module?.roles) return Boolean(module);
  return Boolean(role && module.roles.includes(role));
}

export function getModuleCatalog() {
  return STAFF_ROUTES.map(
    ({ component: _component, icon: _icon, ...module }) => module,
  );
}
