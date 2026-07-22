import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Bot,
  Briefcase,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  Clock,
  FileText,
  FileUp,
  Gavel,
  Headset,
  ListChecks,
  MessageSquare,
  PenLine,
  Scale,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { useAuth } from "../stores/auth";
import NoticiasCard from "../components/NoticiasCard";
import ThemeSelector from "../components/ThemeSelector";
import {
  NOVO_CASO_DOCUMENTO_PATH,
  NOVO_CASO_MANUAL_PATH,
} from "../lib/novoCaso";
import {
  Badge,
  Button,
  EmptyState,
  PageHeader,
  SectionCard,
  StatCard,
  StatusBadge,
  cn,
  fmtDate,
} from "../components/UI";

const MANAGER_ROLES = new Set(["superadmin", "admin", "socio"]);
const CASE_CREATOR_ROLES = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "secretaria",
]);
const LEGAL_ROLES = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "advogado_auxiliar",
  "estagiario",
]);
const CRM_ROLES = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "secretaria",
]);

// Fases encerradas não contam como carteira ativa.
const INACTIVE_CASE_STATUSES = new Set([
  "arquivado",
  "encerrado",
  "cancelado",
  "inativo",
]);

// Tons dos chips da faixa "Prioridades de hoje" (cor + ícone + texto).
const PRIORITY_CHIP_TONE: Record<"red" | "amber" | "blue", string> = {
  red: "bg-danger-50 text-danger-700 ring-danger-200 hover:bg-danger-100",
  amber: "bg-warn-50 text-warn-700 ring-warn-200 hover:bg-warn-100",
  blue: "bg-primary-50 text-primary-700 ring-primary-200 hover:bg-primary-100",
};

// Tons do destaque "Próxima ação recomendada" (wrap + selo + CTA + textos).
const NEXT_ACTION_TONE: Record<
  "red" | "amber",
  {
    wrap: string;
    badge: string;
    cta: string;
    eyebrow: string;
    title: string;
    desc: string;
  }
> = {
  red: {
    wrap: "border-danger-200 bg-danger-50 dark:border-danger-500/25 dark:bg-danger-500/10",
    badge:
      "bg-danger-100 text-danger-700 ring-danger-200 dark:bg-danger-500/15 dark:text-danger-200 dark:ring-danger-500/30",
    cta: "bg-danger-600 text-white hover:bg-danger-700",
    eyebrow: "text-danger-700 dark:text-danger-300",
    title: "text-danger-900 dark:text-danger-100",
    desc: "text-danger-700 dark:text-danger-300/80",
  },
  amber: {
    wrap: "border-warn-200 bg-warn-50 dark:border-warn-500/25 dark:bg-warn-500/10",
    badge:
      "bg-warn-100 text-warn-700 ring-warn-200 dark:bg-warn-500/15 dark:text-warn-200 dark:ring-warn-500/30",
    cta: "bg-warn-600 text-white hover:bg-warn-700",
    eyebrow: "text-warn-700 dark:text-warn-300",
    title: "text-warn-900 dark:text-warn-100",
    desc: "text-warn-700 dark:text-warn-300/80",
  },
};

const AREA_TONES: Record<string, string> = {
  civil: "bg-primary-500",
  trabalhista: "bg-info-500",
  consumidor: "bg-warn-500",
  familia: "bg-primary-300",
  ambiental: "bg-success-500",
  criminal: "bg-danger-500",
  previdenciario: "bg-warn-600",
  empresarial: "bg-primary-700",
  tributario: "bg-info-600",
};

function initials(value?: string) {
  return (value || "?")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function DeadlineBars({
  points,
}: {
  points: Array<{ label: string; value: number }>;
}) {
  const max = Math.max(1, ...points.map((point) => point.value));

  return (
    <div className="grid min-h-52 grid-cols-6 items-end gap-3 pt-4">
      {points.map((point, index) => (
        <div
          key={point.label}
          className="flex h-full min-w-0 flex-col justify-end"
        >
          <div className="mb-2 text-center text-xs font-semibold tabular-nums text-slate-700 dark:text-slate-200">
            {point.value}
          </div>
          <div className="flex h-40 items-end rounded-xl bg-slate-100/80 p-1.5 dark:bg-white/[0.05]">
            <div
              className={cn(
                "w-full rounded-lg transition-all duration-300",
                index === 0 && point.value > 0
                  ? "bg-danger-500"
                  : "bg-primary-600",
              )}
              style={{ height: `${Math.max(8, (point.value / max) * 100)}%` }}
              aria-label={`${point.label}: ${point.value} prazo(s)`}
            />
          </div>
          <div className="mt-2 truncate text-center text-[10px] font-medium text-slate-400">
            {point.label}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function DashboardModern() {
  const { user } = useAuth();
  const [dashboard, setDashboard] = useState<any>(null);
  const [operational, setOperational] = useState<any>(null);
  const [jurimetria, setJurimetria] = useState<any>(null);
  const [prazos, setPrazos] = useState<any[]>([]);
  const [movimentos, setMovimentos] = useState<any[]>([]);
  const [casos, setCasos] = useState<any[]>([]);
  // Bloco incorporado do antigo DashboardIA.
  const [iaSaude, setIaSaude] = useState<any>(null);
  const [solicitacoes, setSolicitacoes] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  // "Gestão do escritório": widgets analíticos/gerenciais, recolhidos por
  // padrão para priorizar o operacional do dia do advogado.
  const [gestaoOpen, setGestaoOpen] = useState(false);
  const [moreActionsOpen, setMoreActionsOpen] = useState(false);

  const currentUser = user as any;
  const firstName = currentUser?.full_name?.split(" ")[0] || "Dr.";
  const isManager = MANAGER_ROLES.has(currentUser?.role || "");
  const canSeeCRM = CRM_ROLES.has(currentUser?.role || "");
  const canCreateCase = CASE_CREATOR_ROLES.has(currentUser?.role || "");
  const canUseLegalAI = LEGAL_ROLES.has(currentUser?.role || "");

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      api.get("/dashboard/"),
      api.get("/dashboard/pendencias-operacionais"),
      // /jurimetria/overview é restrito a sócio+ (403 para advogado/financeiro/
      // estagiário): sem o gate, o widget dispararia um 403 a cada carga.
      isManager
        ? api.get("/jurimetria/overview")
        : Promise.reject(new Error("sem permissão de jurimetria")),
      api.get("/deadlines/?status=pendente&page_size=100"),
      api.get("/movimentos/recentes?limit=8"),
      api.get("/cases/?page_size=200"),
      // /ia-saude é restrito a gestão (403 fora de superadmin/admin/socio):
      // sem o gate, o card ficaria eternamente em "sem dados" para os demais.
      isManager
        ? api.get("/ia-saude/dashboard?dias=30")
        : Promise.reject(new Error("sem permissão de gestão")),
      canSeeCRM
        ? api.get("/atendimentos/solicitacoes-resumo")
        : Promise.reject(new Error("sem permissão de CRM")),
    ])
      .then(
        ([
          dash,
          operationalReq,
          juri,
          deadlines,
          movements,
          cases,
          ia,
          solicitacoesReq,
        ]) => {
          if (dash.status === "fulfilled") setDashboard(dash.value.data);
          if (operationalReq.status === "fulfilled")
            setOperational(operationalReq.value.data);
          if (juri.status === "fulfilled") setJurimetria(juri.value.data);
          if (deadlines.status === "fulfilled")
            setPrazos(asList(deadlines.value.data));
          if (movements.status === "fulfilled")
            setMovimentos(asList(movements.value.data));
          if (cases.status === "fulfilled") setCasos(asList(cases.value.data));
          if (ia.status === "fulfilled") setIaSaude(ia.value.data);
          if (solicitacoesReq.status === "fulfilled")
            setSolicitacoes(solicitacoesReq.value.data);
        },
      )
      .finally(() => setLoading(false));
  }, [canSeeCRM, isManager]);

  const criticalDeadlines = prazos.filter(
    (deadline) => (deadline.dias_restantes ?? 99) <= 3,
  );
  const deadlinesToday = prazos.filter(
    (deadline) => (deadline.dias_restantes ?? 99) === 0,
  ).length;

  const orderedDeadlines = useMemo(
    () =>
      [...prazos]
        .sort((a, b) =>
          String(a.data_prazo || "").localeCompare(String(b.data_prazo || "")),
        )
        .slice(0, 6),
    [prazos],
  );

  const weeklySeries = useMemo(() => {
    const buckets = [0, 0, 0, 0, 0, 0];
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    for (const deadline of prazos) {
      if (!deadline.data_prazo) continue;
      const date = new Date(
        String(deadline.data_prazo).includes("T")
          ? deadline.data_prazo
          : `${deadline.data_prazo}T12:00:00`,
      );
      const week = Math.floor(
        (date.getTime() - today.getTime()) / (7 * 24 * 60 * 60 * 1000),
      );
      if (week < 6) buckets[Math.max(0, week)] += 1;
    }

    return buckets.map((value, index) => ({
      label: index === 0 ? "Esta sem." : `+${index} sem.`,
      value,
    }));
  }, [prazos]);

  const areas = useMemo(() => {
    const totals = new Map<string, number>();
    for (const item of casos) {
      const area = String(item.area || "outros").toLowerCase();
      totals.set(area, (totals.get(area) || 0) + 1);
    }
    return Array.from(totals.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([label, value]) => ({ label, value }));
  }, [casos]);

  // Casos ativos agrupados por fase (visão do dia da carteira).
  const fases = useMemo(() => {
    const totals = new Map<string, number>();
    for (const item of casos) {
      const status = String(item.status || "").toLowerCase();
      if (item.archived_at || INACTIVE_CASE_STATUSES.has(status)) continue;
      const fase = String(item.fase || "sem fase").toLowerCase();
      totals.set(fase, (totals.get(fase) || 0) + 1);
    }
    return Array.from(totals.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([label, value]) => ({ label, value }));
  }, [casos]);

  const successRate =
    jurimetria?.taxa_sucesso_geral != null
      ? Math.round(jurimetria.taxa_sucesso_geral * 100)
      : null;

  // No máximo quatro ações primárias por perfil. Atalhos secundários ficam
  // recolhidos em "Mais ações" para reduzir escolhas simultâneas e impedir
  // navegação para recursos que o perfil não pode executar.
  const primaryActions = [
    ...(canCreateCase
      ? [
          {
            to: NOVO_CASO_DOCUMENTO_PATH,
            label: "Novo caso por documento",
            icon: FileUp,
          },
          {
            to: NOVO_CASO_MANUAL_PATH,
            label: "Novo caso manual",
            icon: PenLine,
          },
        ]
      : []),
    ...(canUseLegalAI
      ? [
          {
            to: "/raio-x",
            label: "Analisar processo externo",
            icon: ScanSearch,
          },
        ]
      : []),
    ...(canSeeCRM
      ? [
          {
            to: "/atividades?tab=relacionamento",
            label: "Registrar atendimento",
            icon: Headset,
          },
        ]
      : []),
  ].slice(0, 4);

  const secondaryActions = [
    ...(canCreateCase
      ? [{ to: "/clientes", label: "Novo cliente", icon: Users }]
      : []),
    ...(canUseLegalAI
      ? [
          { to: "/pecas", label: "Gerar peça", icon: FileText },
          { to: "/inteligencia", label: "Analisar com IA", icon: Sparkles },
          { to: "/ramos", label: "Áreas de Atuação", icon: Scale },
        ]
      : []),
  ];

  const visiblePrimaryActions = primaryActions.length
    ? primaryActions
    : [
        {
          to: "/atividades",
          label: "Abrir agenda e prazos",
          icon: CalendarClock,
        },
      ];

  // Faixa "Prioridades de hoje": o que exige atenção AGORA, como atalhos.
  // Usa dados já carregados; só mostra o que tem contagem > 0. `clientes
  // aguardando` só aparece para quem enxerga o CRM (RBAC preservado).
  const priorityItems: Array<{
    key: string;
    count: number;
    label: string;
    to: string;
    tone: "red" | "amber" | "blue";
    icon: typeof AlertTriangle;
  }> = [
    {
      key: "acoes-vencidas",
      count: Number(
        operational?.contagens?.proximas_acoes_vencidas ?? 0,
      ),
      label: "próximas ações vencidas",
      to: "/casos",
      tone: "red",
      icon: AlertTriangle,
    },
    {
      key: "sem-acao",
      count: Number(operational?.contagens?.casos_sem_proxima_acao ?? 0),
      label: "casos sem próxima ação",
      to: "/casos",
      tone: "amber",
      icon: ListChecks,
    },
    {
      key: "prazos-sem-conferencia",
      count: Number(operational?.contagens?.prazos_sem_conferencia ?? 0),
      label: "prazos sem conferência",
      to: "/atividades?tipo=prazo",
      tone: "red",
      icon: ShieldCheck,
    },
    {
      key: "intimacoes",
      count: Number(
        operational?.contagens?.intimacoes_nao_analisadas ?? 0,
      ),
      label: "intimações não analisadas",
      to: "/intimacoes",
      tone: "blue",
      icon: Gavel,
    },
    {
      key: "tarefas-vencidas",
      count: Number(operational?.contagens?.tarefas_vencidas ?? 0),
      label: "tarefas vencidas",
      to: "/atividades?tipo=tarefa",
      tone: "amber",
      icon: ListChecks,
    },
    {
      key: "pecas-revisao",
      count: Number(operational?.contagens?.pecas_em_revisao ?? 0),
      label: "peças em revisão",
      to: "/pecas",
      tone: "blue",
      icon: FileText,
    },
    {
      key: "documentos-aguardados",
      count: Number(operational?.contagens?.documentos_aguardados ?? 0),
      label: "documentos aguardados",
      to: "/documentos",
      tone: "amber",
      icon: FileText,
    },
    {
      key: "prazos",
      count: criticalDeadlines.length,
      label: "prazos críticos",
      to: "/atividades?tipo=prazo",
      tone: "red",
      icon: AlertTriangle,
    },
    {
      key: "hoje",
      count: deadlinesToday,
      label: "vencendo hoje",
      to: "/atividades",
      tone: "amber",
      icon: Clock,
    },
    ...(canSeeCRM
      ? [
          {
            key: "clientes",
            count: Number(solicitacoes?.pendentes ?? 0),
            label: "clientes aguardando",
            to: "/atividades?tab=relacionamento",
            tone: "amber" as const,
            icon: MessageSquare,
          },
        ]
      : []),
  ];
  const activePriorities = priorityItems.filter((item) => item.count > 0);

  // "Próxima ação recomendada": UM único item, o mais urgente, derivado só de
  // dados já carregados. Prioridade: prazo crítico/vencido → prazo de hoje →
  // cliente aguardando resposta → nada (estado calmo). Sem fonte, retorna null.
  type NextAction = {
    tone: "red" | "amber";
    icon: typeof AlertTriangle;
    eyebrow: string;
    title: string;
    desc: string;
    cta: string;
    to: string;
  };
  const nextAction = useMemo<NextAction | null>(() => {
    // 1) Próxima ação canônica do caso, priorizada no backend com RBAC.
    const operationalHighlight = operational?.destaque;
    if (operationalHighlight) {
      const dueAt = new Date(operationalHighlight.due_at);
      const overdue = dueAt.getTime() < Date.now();
      return {
        tone: overdue ? "red" : "amber",
        icon: ListChecks,
        eyebrow: overdue
          ? "Próxima ação vencida"
          : operationalHighlight.blocked
            ? "Próxima ação bloqueada"
            : "Próxima ação do caso",
        title: operationalHighlight.title,
        desc: `${operationalHighlight.case_title} — responsável definido, prazo ${fmtDate(
          operationalHighlight.due_at,
        )}.`,
        cta: "Abrir caso",
        to: `/casos/${operationalHighlight.case_id}`,
      };
    }

    const missingCase = operational?.casos_sem_proxima_acao?.[0];
    if (missingCase) {
      return {
        tone: "amber",
        icon: ListChecks,
        eyebrow: "Caso sem próxima ação",
        title: missingCase.titulo,
        desc:
          "Defina responsável, providência, data esperada e origem da obrigação.",
        cta: "Organizar caso",
        to: `/casos/${missingCase.id}`,
      };
    }

    // 2) Prazo crítico/vencido (inclui "vence hoje"), o de menor folga.
    const critical = [...prazos]
      .filter((deadline) => (deadline.dias_restantes ?? 99) <= 3)
      .sort((a, b) => (a.dias_restantes ?? 99) - (b.dias_restantes ?? 99))[0];
    if (critical) {
      const days = critical.dias_restantes ?? 0;
      return {
        tone: "red",
        icon: AlertTriangle,
        eyebrow:
          days < 0
            ? "Prazo vencido"
            : days === 0
              ? "Prazo vence hoje"
              : `Prazo crítico · ${days} dia(s)`,
        title: critical.titulo || "Prazo sem título",
        desc: critical.case_title
          ? `${critical.case_title} — vence ${fmtDate(critical.data_prazo)}. Confirme a ciência e registre a providência.`
          : `Vence ${fmtDate(critical.data_prazo)}. Confirme a ciência e registre a providência.`,
        cta: "Ver e confirmar",
        to: "/atividades?tipo=prazo",
      };
    }
    // 3) Cliente aguardando resposta (só quem enxerga o CRM).
    if (canSeeCRM && Number(solicitacoes?.pendentes ?? 0) > 0) {
      const pending = Number(solicitacoes?.pendentes ?? 0);
      const late = Number(solicitacoes?.atrasadas ?? 0);
      return {
        tone: "amber",
        icon: MessageSquare,
        eyebrow: late > 0 ? `${late} atrasada(s)` : "Cliente aguardando",
        title: `${pending} solicitação(ões) de cliente pendente(s)`,
        desc:
          late > 0
            ? "Abra a linha do tempo prioritária, responda e registre o atendimento."
            : "Responda e registre o atendimento na linha do tempo prioritária.",
        cta: "Responder",
        to: solicitacoes?.destaque?.client_id
          ? `/clientes/${solicitacoes.destaque.client_id}?tab=atendimentos`
          : "/atividades?tab=relacionamento",
      };
    }
    // 3) Nada urgente → estado calmo (renderizado no JSX).
    return null;
  }, [operational, prazos, canSeeCRM, solicitacoes]);
  const NextActionIcon = nextAction?.icon;

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Meu dia"
        title={`Bom trabalho, ${firstName}`}
        subtitle="Prioridades, agenda e casos recentes para trabalhar com tranquilidade."
        actions={<ThemeSelector className="w-full sm:min-w-[330px]" />}
      />

      {/* ===================== MEU DIA ===================== */}
      {/* Prioridade operacional do advogado: ações, pendências, agenda e
          casos recentes. KPIs/indicadores gerenciais saem do topo. */}
      <section aria-label="Meu dia" className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-50 text-primary-600">
            <CalendarClock className="h-4 w-4" />
          </span>
          <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
            Meu dia
          </h2>
          <span className="text-sm text-slate-500 dark:text-slate-400">
            O que precisa de você agora
          </span>
        </div>

        {/* Próxima ação recomendada — UM item, o mais urgente, derivado dos
          dados já carregados (prazo crítico/vencido → cliente aguardando).
          Sem nada urgente, mostra o estado calmo com atalho para a agenda. */}
        {!loading &&
          (nextAction ? (
            <Link
              to={nextAction.to}
              aria-label={`Próxima ação recomendada: ${nextAction.title}`}
              className={cn(
                "group flex flex-col gap-4 rounded-xl border p-4 transition sm:flex-row sm:items-center sm:justify-between",
                NEXT_ACTION_TONE[nextAction.tone].wrap,
              )}
            >
              <div className="flex items-start gap-4">
                <span
                  className={cn(
                    "shrink-0 rounded-xl p-3 ring-1 ring-inset",
                    NEXT_ACTION_TONE[nextAction.tone].badge,
                  )}
                >
                  {NextActionIcon && <NextActionIcon className="h-6 w-6" />}
                </span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={cn(
                        "text-[11px] font-semibold uppercase tracking-[0.16em]",
                        NEXT_ACTION_TONE[nextAction.tone].eyebrow,
                      )}
                    >
                      {nextAction.eyebrow}
                    </span>
                    <Badge tone="blue">Próxima ação recomendada</Badge>
                  </div>
                  <h3
                    className={cn(
                      "mt-1 truncate text-lg font-semibold",
                      NEXT_ACTION_TONE[nextAction.tone].title,
                    )}
                  >
                    {nextAction.title}
                  </h3>
                  <p
                    className={cn(
                      "mt-1 text-sm leading-6",
                      NEXT_ACTION_TONE[nextAction.tone].desc,
                    )}
                  >
                    {nextAction.desc}
                  </p>
                </div>
              </div>
              <span
                className={cn(
                  "inline-flex shrink-0 items-center justify-center gap-2 rounded-lg px-4 py-2 text-[13px] font-bold transition",
                  NEXT_ACTION_TONE[nextAction.tone].cta,
                )}
              >
                {nextAction.cta}
                <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" />
              </span>
            </Link>
          ) : (
            <Link
              to="/atividades"
              aria-label="Nada urgente para agora — ver agenda"
              className="group flex items-center justify-between gap-4 rounded-xl border border-success-100 bg-success-50 p-4 transition dark:border-success-500/20 dark:bg-success-500/10"
            >
              <div className="flex items-center gap-4">
                <span className="shrink-0 rounded-xl bg-success-100 p-3 text-success-700 ring-1 ring-inset ring-success-200 dark:bg-success-500/15 dark:text-success-300">
                  <CheckCircle2 className="h-6 w-6" />
                </span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-success-700 dark:text-success-300">
                      Tudo sob controle
                    </span>
                    <Badge tone="blue">Próxima ação recomendada</Badge>
                  </div>
                  <h3 className="mt-1 text-lg font-semibold text-success-800 dark:text-success-200">
                    Nada urgente para agora
                  </h3>
                  <p className="mt-1 text-sm leading-6 text-success-700 dark:text-success-300/80">
                    Nenhum prazo crítico ou cliente aguardando. Aproveite para
                    revisar a agenda com calma.
                  </p>
                </div>
              </div>
              <span className="inline-flex shrink-0 items-center gap-2 text-sm font-semibold text-success-700 dark:text-success-300">
                Ver agenda
                <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" />
              </span>
            </Link>
          ))}

        {/* Faixa "Prioridades de hoje" — o que exige atenção agora, com atalho.
          Vem ANTES do painel de ações: "o que preciso resolver?" primeiro. */}
        <section
          aria-label="Prioridades de hoje"
          className="rounded-xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex shrink-0 items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
              <ListChecks className="h-4 w-4 text-ouro" />
              Prioridades de hoje
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {loading ? (
                <span className="text-sm text-slate-400">
                  Carregando prioridades…
                </span>
              ) : activePriorities.length ? (
                activePriorities.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.key}
                      to={item.to}
                      className={cn(
                        "group inline-flex items-center gap-2 rounded-xl px-3 py-1.5 text-sm font-medium ring-1 ring-inset transition",
                        PRIORITY_CHIP_TONE[item.tone],
                      )}
                    >
                      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                      <span className="text-base font-semibold tabular-nums">
                        {item.count}
                      </span>
                      <span>{item.label}</span>
                      <ArrowRight className="h-3.5 w-3.5 shrink-0 opacity-0 transition group-hover:translate-x-0.5 group-hover:opacity-100" />
                    </Link>
                  );
                })
              ) : (
                <span className="inline-flex items-center gap-2 rounded-xl bg-success-50 px-3 py-1.5 text-sm font-medium text-success-700 ring-1 ring-inset ring-success-200">
                  <CheckCircle2
                    className="h-4 w-4 shrink-0"
                    aria-hidden="true"
                  />
                  Sem pendências críticas para hoje
                </span>
              )}
            </div>
          </div>
        </section>

        {/* Painel de AÇÕES — vem DEPOIS das prioridades: resolvido o urgente,
          "o que quero iniciar?". Mantém as 4 ações principais do Command
          Center (documento IA · manual · Raio-X · atendimento). */}
        <section className="relative overflow-hidden rounded-xl border border-slate-200 bg-white p-4 before:absolute before:inset-x-0 before:top-0 before:h-[3px] before:bg-ouro-claro dark:border-white/10 dark:bg-white/[0.03] md:p-5">
          <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
            <div className="max-w-2xl">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                {/* tone="blue" (pill clara + texto ouro-profundo) — as classes
                  extras bg-white/10 + text-primary-100 disputavam com o tone
                  padrão slate e o badge ficava ilegível no fundo sépia. */}
                <Badge tone="blue">Operação segura</Badge>
                <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  Auditoria e LGPD preservadas
                </span>
              </div>
              {/* !text-white: o seletor global `.ejc-modern-scope h2` (index.css)
                pinta headings de #111827 e vencia o utilitário text-white,
                deixando o título ilegível sobre o gradiente sépia escuro. */}
              <h2 className="text-lg font-bold text-slate-900 dark:!text-slate-100">
                Inicie uma nova frente de trabalho
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                Resolvidas as prioridades acima, escolha a ação principal. Tudo
                com trilha de auditoria e sem substituir a validação
                profissional do advogado.
              </p>
            </div>
            <div className="flex flex-col items-start gap-2 xl:items-end">
              <div className="flex flex-wrap gap-2 xl:justify-end">
                {visiblePrimaryActions.map(({ to, label, icon: Icon }) => (
                  <Link key={label} to={to}>
                    <Button
                      variant="primary"
                      icon={<Icon className="h-4 w-4" />}
                      className="shadow-sm"
                    >
                      {label}
                    </Button>
                  </Link>
                ))}
              </div>
              {secondaryActions.length > 0 && (
                <div className="flex flex-wrap items-center gap-2 xl:justify-end">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setMoreActionsOpen((open) => !open)}
                    aria-expanded={moreActionsOpen}
                    aria-controls="acoes-secundarias-dashboard"
                    className="text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-white/10"
                  >
                    Mais ações
                    <ChevronDown
                      className={cn(
                        "ml-1 h-4 w-4 transition-transform",
                        moreActionsOpen && "rotate-180",
                      )}
                      aria-hidden="true"
                    />
                  </Button>
                  {moreActionsOpen && (
                    <div
                      id="acoes-secundarias-dashboard"
                      className="flex flex-wrap gap-2"
                    >
                      {secondaryActions.map(({ to, label, icon: Icon }) => (
                        <Link key={label} to={to}>
                          <Button
                            variant="ghost"
                            size="sm"
                            icon={<Icon className="h-4 w-4" />}
                            className="text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-white/10"
                          >
                            {label}
                          </Button>
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </section>

        {canUseLegalAI && (
          <Link
            to="/raio-x"
            className="group flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4 transition sm:flex-row sm:items-center sm:justify-between dark:border-white/10 dark:bg-white/[0.03]"
          >
            <div className="flex items-start gap-4">
              <span className="rounded-xl bg-ouro/10 p-3 text-ouro-profundo ring-1 ring-inset ring-ouro/20 dark:text-ouro-claro">
                <ScanSearch className="h-6 w-6" />
              </span>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-[15px] font-bold">
                    Analisar antes de cadastrar
                  </h2>
                  <Badge tone="blue">Raio-X preliminar</Badge>
                </div>
                <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-500">
                  Envie documentos externos, confira o diagnóstico e só
                  transforme em caso após a decisão humana. A análise não altera
                  a carteira nem os indicadores oficiais.
                </p>
              </div>
            </div>
            <span className="inline-flex shrink-0 items-center gap-2 text-sm font-semibold text-ouro-profundo dark:text-ouro-claro">
              Abrir Raio-X
              <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" />
            </span>
          </Link>
        )}

        <div className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
          <SectionCard
            title="Agenda e prazos próximos"
            subtitle="Itens ordenados por data para tratamento imediato."
            actions={
              <Link
                to="/atividades"
                className="text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300"
              >
                Abrir central
              </Link>
            }
          >
            {loading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((item) => (
                  <div
                    key={item}
                    className="h-16 animate-pulse rounded-xl bg-slate-100 dark:bg-white/[0.05]"
                  />
                ))}
              </div>
            ) : orderedDeadlines.length === 0 ? (
              <EmptyState
                title="Nenhum prazo pendente"
                message="A agenda operacional está limpa para os filtros atuais."
                icon={CalendarClock}
              />
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-white/[0.07]">
                {orderedDeadlines.map((deadline, index) => {
                  const days = deadline.dias_restantes ?? 99;
                  const tone =
                    days <= 0 ? "red" : days <= 3 ? "amber" : "slate";
                  return (
                    <Link
                      key={deadline.id ?? index}
                      to="/atividades"
                      className="flex items-center gap-4 rounded-xl px-2 py-3 transition-colors hover:bg-slate-50 dark:hover:bg-white/[0.04]"
                    >
                      <div className="flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-xl border border-black/[0.05] bg-white dark:border-white/10 dark:bg-white/[0.04]">
                        <span className="text-sm font-semibold text-slate-950 dark:text-slate-100">
                          {deadline.data_prazo
                            ? new Date(deadline.data_prazo).getDate()
                            : "--"}
                        </span>
                        <span className="text-[10px] uppercase text-slate-400">
                          dia
                        </span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-semibold text-slate-950 dark:text-slate-100">
                          {deadline.titulo || "Prazo sem título"}
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                          <Clock className="h-3.5 w-3.5" />
                          {fmtDate(deadline.data_prazo)}
                          {deadline.case_title && (
                            <span className="truncate">
                              • {deadline.case_title}
                            </span>
                          )}
                        </div>
                      </div>
                      <Badge tone={tone}>
                        {days < 0
                          ? "Vencido"
                          : days === 0
                            ? "Hoje"
                            : `${days} dias`}
                      </Badge>
                    </Link>
                  );
                })}
              </div>
            )}
          </SectionCard>

          <SectionCard
            title="Alertas inteligentes"
            subtitle="Sinais para priorização, não decisões automatizadas."
            actions={
              <Sparkles className="h-4 w-4 text-ai-600 dark:text-ai-300" />
            }
          >
            <div className="space-y-3">
              {canSeeCRM && (
                <Link
                  to={
                    solicitacoes?.destaque?.client_id
                      ? `/clientes/${solicitacoes.destaque.client_id}?tab=atendimentos`
                      : "/clientes"
                  }
                  className={cn(
                    "group block rounded-xl border p-4",
                    solicitacoes?.atrasadas
                      ? "border-danger-100 bg-danger-50 dark:border-danger-500/20 dark:bg-danger-500/10"
                      : "border-primary-100 bg-primary-50 dark:border-primary-500/20 dark:bg-primary-500/10",
                  )}
                >
                  <div className="flex items-start gap-3">
                    <MessageSquare
                      className={cn(
                        "mt-0.5 h-4 w-4",
                        solicitacoes?.atrasadas
                          ? "text-danger-600 dark:text-danger-300"
                          : "text-primary-700 dark:text-primary-300",
                      )}
                    />
                    <div>
                      <div
                        className={cn(
                          "text-sm font-semibold",
                          solicitacoes?.atrasadas
                            ? "text-danger-800 dark:text-danger-200"
                            : "text-primary-900 dark:text-primary-200",
                        )}
                      >
                        {solicitacoes?.pendentes ?? 0} solicitação(ões) de
                        cliente pendente(s)
                      </div>
                      <p
                        className={cn(
                          "mt-1 text-xs",
                          solicitacoes?.atrasadas
                            ? "text-danger-700 dark:text-danger-300/80"
                            : "text-primary-700 dark:text-primary-300/80",
                        )}
                      >
                        {solicitacoes?.atrasadas
                          ? `${solicitacoes.atrasadas} atrasada(s); abra a linha do tempo prioritária.`
                          : "Acompanhe prazo, responsável e confirmação de atendimento."}
                      </p>
                      <span
                        className={cn(
                          "mt-2 inline-flex items-center gap-1 text-xs font-semibold",
                          solicitacoes?.atrasadas
                            ? "text-danger-700 dark:text-danger-300"
                            : "text-primary-700 dark:text-primary-300",
                        )}
                      >
                        Ver e responder
                        <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" />
                      </span>
                    </div>
                  </div>
                </Link>
              )}
              <Link
                to="/atividades?tipo=prazo"
                className="group block rounded-xl border border-danger-100 bg-danger-50 p-4 dark:border-danger-500/20 dark:bg-danger-500/10"
              >
                <div className="flex items-start gap-3">
                  <AlertTriangle className="mt-0.5 h-4 w-4 text-danger-600 dark:text-danger-300" />
                  <div>
                    <div className="text-sm font-semibold text-danger-800 dark:text-danger-200">
                      {criticalDeadlines.length} prazo(s) crítico(s)
                    </div>
                    <p className="mt-1 text-xs text-danger-700 dark:text-danger-300/80">
                      Priorize vencimentos em até três dias e registre a
                      providência adotada.
                    </p>
                    <span className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-danger-700 dark:text-danger-300">
                      Ver e confirmar
                      <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" />
                    </span>
                  </div>
                </div>
              </Link>
              <Link
                to="/inteligencia"
                className="group block rounded-xl border border-ai-100 bg-ai-50 p-4 dark:border-ai-500/20 dark:bg-ai-500/10"
              >
                <div className="flex items-start gap-3">
                  <Bot className="mt-0.5 h-4 w-4 text-ai-700 dark:text-ai-300" />
                  <div>
                    <div className="text-sm font-semibold text-ai-900 dark:text-ai-200">
                      IA jurídica assistiva
                    </div>
                    <p className="mt-1 text-xs text-ai-800 dark:text-ai-300/80">
                      Rascunhos e análises exigem conferência das fontes e
                      revisão humana antes do uso.
                    </p>
                    <span className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-ai-800 dark:text-ai-300">
                      Abrir IA jurídica
                      <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" />
                    </span>
                  </div>
                </div>
              </Link>
              <div className="rounded-xl border border-success-100 bg-success-50 p-4 dark:border-success-500/20 dark:bg-success-500/10">
                <div className="flex items-start gap-3">
                  <ShieldCheck className="mt-0.5 h-4 w-4 text-success-700 dark:text-success-300" />
                  <div>
                    <div className="text-sm font-semibold text-success-800 dark:text-success-200">
                      Segurança por desenho
                    </div>
                    <p className="mt-1 text-xs text-success-700 dark:text-success-300/80">
                      A interface não amplia permissões; o backend continua
                      sendo a fonte de verdade do RBAC.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </SectionCard>
        </div>

        <div className="grid gap-5 xl:grid-cols-2">
          <SectionCard
            title="Casos recentes"
            subtitle="Acesso rápido à carteira ativa."
            actions={
              <Link
                to="/casos"
                className="text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300"
              >
                Ver casos
              </Link>
            }
          >
            {casos.length === 0 ? (
              <EmptyState title="Sem casos recentes" icon={Briefcase} />
            ) : (
              <div className="space-y-2.5">
                {casos.slice(0, 6).map((item) => (
                  <Link
                    key={item.id}
                    to={`/casos/${item.id}`}
                    className="flex items-center gap-3 rounded-xl border border-black/[0.05] bg-white p-3 transition-colors hover:border-primary-200 hover:bg-primary-50/40 dark:border-white/10 dark:bg-white/[0.03] dark:hover:bg-white/[0.06]"
                  >
                    <div
                      className={cn(
                        "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-xs font-semibold text-white",
                        AREA_TONES[String(item.area || "").toLowerCase()] ||
                          "bg-slate-700",
                      )}
                    >
                      {initials(item.titulo || item.numero_interno)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold text-slate-950 dark:text-slate-100">
                        {item.titulo ||
                          item.numero_interno ||
                          "Caso sem título"}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-2">
                        {item.area && <Badge tone="blue">{item.area}</Badge>}
                        <StatusBadge value={item.status} />
                      </div>
                    </div>
                    <ArrowRight className="h-4 w-4 text-slate-400" />
                  </Link>
                ))}
              </div>
            )}
          </SectionCard>

          <SectionCard
            title="Atividade recente"
            subtitle="Movimentações registradas na operação jurídica."
            actions={
              <Link
                to="/atividades"
                className="text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300"
              >
                Ver atividades
              </Link>
            }
          >
            {movimentos.length === 0 ? (
              <EmptyState title="Sem movimentações recentes" icon={Gavel} />
            ) : (
              <div className="space-y-2.5">
                {movimentos.slice(0, 6).map((movement, index) => (
                  <Link
                    key={movement.id ?? index}
                    to={
                      movement.case_id
                        ? `/casos/${movement.case_id}`
                        : "/atividades"
                    }
                    className="flex items-start gap-3 rounded-xl border border-black/[0.04] bg-white p-3 transition-colors hover:bg-slate-50 dark:border-white/[0.07] dark:bg-white/[0.03] dark:hover:bg-white/[0.06]"
                  >
                    <div className="mt-0.5 rounded-lg bg-primary-50 p-2 text-primary-700 dark:bg-primary-400/10 dark:text-primary-300">
                      <Gavel className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="line-clamp-2 text-sm text-slate-700 dark:text-slate-200">
                        {movement.descricao || "Movimentação registrada"}
                      </div>
                      <div className="mt-1 text-xs text-slate-400">
                        {fmtDate(movement.quando || movement.created_at)}
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </SectionCard>
        </div>

        {/* A grade extensa de atalhos para módulos foi removida — "Mais
          Ferramentas" no menu cumpre esse papel. */}
        <NoticiasCard />
      </section>

      {/* ================= GESTÃO DO ESCRITÓRIO ================= */}
      {/* Widgets analíticos/gerenciais, recolhidos por padrão. Dados
          financeiros ficam concentrados no módulo Financeiro. */}
      {isManager && (
        <section
          aria-label="Gestão do escritório"
          className="rounded-xl border border-slate-200 bg-white dark:border-white/10 dark:bg-white/[0.03]"
        >
          <button
            type="button"
            onClick={() => setGestaoOpen((open) => !open)}
            aria-expanded={gestaoOpen}
            aria-controls="gestao-escritorio-conteudo"
            className="flex w-full items-center justify-between gap-3 rounded-xl px-4 py-3 text-left transition-colors hover:bg-slate-50 dark:hover:bg-white/[0.04]"
          >
            <span className="flex min-w-0 items-center gap-2">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-700 dark:bg-primary-400/10 dark:text-primary-300">
                <BarChart3 className="h-4 w-4" />
              </span>
              <span className="text-base font-semibold text-slate-900 dark:text-slate-100">
                Gestão do escritório
              </span>
              <span className="hidden text-sm text-slate-500 dark:text-slate-400 sm:inline">
                Indicadores, gráficos, jurimetria e saúde da IA
              </span>
            </span>
            <ChevronDown
              className={cn(
                "h-5 w-5 shrink-0 text-slate-400 transition-transform",
                gestaoOpen && "rotate-180",
              )}
              aria-hidden="true"
            />
          </button>
          {gestaoOpen && (
            <div
              id="gestao-escritorio-conteudo"
              className="space-y-5 border-t border-slate-100 p-4 dark:border-white/[0.07]"
            >
              <div
                className={cn(
                  "grid gap-5 sm:grid-cols-2",
                  canSeeCRM ? "xl:grid-cols-5" : "xl:grid-cols-4",
                )}
              >
                <StatCard
                  label="Casos ativos"
                  value={dashboard?.casos?.ativos ?? "—"}
                  subtitle={
                    dashboard?.casos?.total
                      ? `${dashboard.casos.total} casos cadastrados`
                      : "Carteira atual"
                  }
                  icon={<Briefcase className="h-5 w-5" />}
                  tone="blue"
                />
                <StatCard
                  label="Prazos críticos"
                  value={criticalDeadlines.length}
                  subtitle={`${deadlinesToday} vencendo hoje`}
                  icon={<AlertTriangle className="h-5 w-5" />}
                  tone={criticalDeadlines.length ? "red" : "amber"}
                  trend={criticalDeadlines.length ? "down" : undefined}
                />
                <StatCard
                  label="Movimentações"
                  value={movimentos.length}
                  subtitle="Atividades recentes"
                  icon={<Gavel className="h-5 w-5" />}
                  tone="green"
                />
                <StatCard
                  label="Taxa de êxito"
                  value={successRate != null ? `${successRate}%` : "—"}
                  subtitle="Base jurimétrica disponível"
                  icon={<BarChart3 className="h-5 w-5" />}
                  tone="amber"
                />
                {canSeeCRM && (
                  <StatCard
                    label="Solicitações de clientes"
                    value={solicitacoes?.pendentes ?? "—"}
                    subtitle={
                      solicitacoes
                        ? `${solicitacoes.atrasadas} atrasada(s) · ${solicitacoes.proximas_24h} em 24h`
                        : "Linha do tempo de atendimento"
                    }
                    icon={<MessageSquare className="h-5 w-5" />}
                    tone={solicitacoes?.atrasadas ? "red" : "blue"}
                  />
                )}
              </div>

              <div className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
                <SectionCard
                  title="Prazos das próximas semanas"
                  subtitle="Distribuição temporal dos compromissos pendentes."
                  actions={
                    <Link
                      to="/atividades?tipo=prazo"
                      className="text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300"
                    >
                      Ver prazos
                    </Link>
                  }
                >
                  {loading ? (
                    <div className="h-52 animate-pulse rounded-xl bg-slate-100 dark:bg-white/[0.05]" />
                  ) : (
                    <DeadlineBars points={weeklySeries} />
                  )}
                </SectionCard>

                <SectionCard
                  title="Carteira por área"
                  subtitle="Concentração dos casos cadastrados."
                >
                  {areas.length === 0 ? (
                    <EmptyState
                      title="Sem casos na carteira"
                      icon={Briefcase}
                    />
                  ) : (
                    <div className="space-y-3">
                      {areas.map((area, index) => {
                        const max = Math.max(
                          1,
                          ...areas.map((item) => item.value),
                        );
                        return (
                          <div key={area.label}>
                            <div className="mb-1.5 flex items-center justify-between gap-3 text-xs">
                              <span className="truncate font-medium capitalize text-slate-600 dark:text-slate-300">
                                {area.label}
                              </span>
                              <span className="font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                                {area.value}
                              </span>
                            </div>
                            <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-white/[0.06]">
                              <div
                                className={cn(
                                  "h-full rounded-full",
                                  [
                                    "bg-primary-700",
                                    "bg-primary-500",
                                    "bg-primary-300",
                                    "bg-slate-500",
                                    "bg-success-500",
                                    "bg-warn-500",
                                  ][index],
                                )}
                                style={{
                                  width: `${Math.max(8, (area.value / max) * 100)}%`,
                                }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </SectionCard>
              </div>

              <div className="grid gap-5 xl:grid-cols-2">
                <SectionCard
                  title="Casos ativos por fase"
                  subtitle="Andamento da carteira em cada etapa."
                  actions={
                    <Link
                      to="/casos"
                      className="text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300"
                    >
                      Ver casos
                    </Link>
                  }
                >
                  {fases.length === 0 ? (
                    <EmptyState title="Sem casos ativos" icon={Briefcase} />
                  ) : (
                    <div className="space-y-3">
                      {fases.map((fase) => {
                        const max = Math.max(
                          1,
                          ...fases.map((item) => item.value),
                        );
                        return (
                          <div key={fase.label}>
                            <div className="mb-1.5 flex items-center justify-between gap-3 text-xs">
                              <span className="truncate font-medium capitalize text-slate-600 dark:text-slate-300">
                                {fase.label.replace(/_/g, " ")}
                              </span>
                              <span className="font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                                {fase.value}
                              </span>
                            </div>
                            <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-white/[0.06]">
                              <div
                                className="h-full rounded-full bg-primary-600"
                                style={{
                                  width: `${Math.max(8, (fase.value / max) * 100)}%`,
                                }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </SectionCard>

                {isManager && (
                  <SectionCard
                    title="Saúde da IA"
                    subtitle="Uso e aproveitamento nos últimos 30 dias."
                    actions={
                      <Link
                        to="/inteligencia?tab=saude"
                        className="text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300"
                      >
                        Detalhes
                      </Link>
                    }
                  >
                    {iaSaude ? (
                      <div className="grid grid-cols-2 gap-3">
                        {[
                          {
                            label: "Chamadas",
                            value: iaSaude.total_chamadas ?? 0,
                          },
                          {
                            label: "Aproveitamento",
                            value:
                              iaSaude.taxa_aproveitamento_pct != null
                                ? `${iaSaude.taxa_aproveitamento_pct}%`
                                : "—",
                          },
                          {
                            label: "PII removida",
                            value: iaSaude.chamadas_com_pii_removida ?? 0,
                          },
                        ].map(({ label, value }) => (
                          <div
                            key={label}
                            className="rounded-xl border border-black/[0.05] bg-white p-3 dark:border-white/10 dark:bg-white/[0.03]"
                          >
                            <div className="text-xs text-slate-400">
                              {label}
                            </div>
                            <div className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-100">
                              {value}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <EmptyState
                        title="Sem dados de uso da IA"
                        message="As métricas aparecem após as primeiras chamadas assistidas."
                        icon={Bot}
                      />
                    )}
                  </SectionCard>
                )}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
