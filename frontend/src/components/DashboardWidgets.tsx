import { useMemo } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Bot,
  Briefcase,
  CalendarClock,
  CheckCircle2,
  Clock,
  FileText,
  Gavel,
  MessageSquare,
  Scale,
  Sparkles,
  Users,
} from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../stores/auth";
import {
  BentoGrid,
  BentoGridCell,
  BentoGridContent,
  BentoGridFooter,
  BentoGridHeader,
} from "./ui/BentoGrid";
import { Badge, Button, SkeletonCard, cn, fmtDate } from "./UI";

/**
 * Widgets modulares para o Dashboard Bento Grid.
 * Cada widget é autocontido e pode ser recombinado livremente.
 */

// ==================== WIDGET: PRIORIDADES DE HOJE ====================

interface PriorityItem {
  key: string;
  count: number;
  label: string;
  to: string;
  tone: "red" | "amber" | "blue";
  icon: any;
}

export function PrioridadesHojeWidget({
  criticalDeadlines,
  deadlinesToday,
  solicitacoesPendentes,
  canSeeCRM,
}: {
  criticalDeadlines: number;
  deadlinesToday: number;
  solicitacoesPendentes: number;
  canSeeCRM: boolean;
}) {
  const priorityItems: PriorityItem[] = useMemo(
    () => [
      {
        key: "prazos",
        count: criticalDeadlines,
        label: "prazos críticos",
        to: "/atividades?tipo=prazo",
        tone: "red" as const,
        icon: AlertTriangle,
      },
      {
        key: "hoje",
        count: deadlinesToday,
        label: "vencendo hoje",
        to: "/atividades",
        tone: "amber" as const,
        icon: Clock,
      },
      ...(canSeeCRM
        ? [
            {
              key: "clientes",
              count: solicitacoesPendentes,
              label: "clientes aguardando",
              to: "/atividades?tab=relacionamento",
              tone: "amber" as const,
              icon: MessageSquare,
            },
          ]
        : []),
    ],
    [criticalDeadlines, deadlinesToday, solicitacoesPendentes, canSeeCRM],
  );

  const activePriorities = priorityItems.filter((item) => item.count > 0);

  if (activePriorities.length === 0) {
    return (
      <BentoGridCell variant="default" className="flex min-h-40 items-center justify-center">
        <div className="text-center">
          <CheckCircle2 className="mx-auto mb-2 h-8 w-8 text-success-500" />
          <p className="text-sm font-medium text-slate-600 dark:text-slate-300">
            Tudo em dia!
          </p>
          <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
            Nenhuma prioridade urgente no momento.
          </p>
        </div>
      </BentoGridCell>
    );
  }

  const toneStyles = {
    red: "bg-danger-50 text-danger-700 ring-danger-200 hover:bg-danger-100 dark:bg-danger-900/30 dark:text-danger-300 dark:ring-danger-700/50",
    amber: "bg-warn-50 text-warn-700 ring-warn-200 hover:bg-warn-100 dark:bg-warn-900/30 dark:text-warn-300 dark:ring-warn-700/50",
    blue: "bg-primary-50 text-primary-700 ring-primary-200 hover:bg-primary-100 dark:bg-primary-900/30 dark:text-primary-300 dark:ring-primary-700/50",
  };

  return (
    <BentoGridCell variant="warning" colSpan={2}>
      <BentoGridHeader
        eyebrow="Atenção necessária"
        title="Prioridades de hoje"
        subtitle={`${activePriorities.length} item(s) requer(em) ação`}
      />
      <BentoGridContent>
        <div className="flex flex-wrap gap-2">
          {activePriorities.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.key}
                to={item.to}
                className={cn(
                  "inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium ring-1 transition-colors",
                  toneStyles[item.tone],
                )}
              >
                <Icon className="h-4 w-4" />
                <span className="font-semibold">{item.count}</span>
                <span className="hidden sm:inline">{item.label}</span>
                <ArrowRight className="ml-1 h-3 w-3 opacity-60" />
              </Link>
            );
          })}
        </div>
      </BentoGridContent>
      <BentoGridFooter>
        <Link
          to="/atividades"
          className="text-xs font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400"
        >
          Ver todas as atividades →
        </Link>
      </BentoGridFooter>
    </BentoGridCell>
  );
}

// ==================== WIDGET: PRÓXIMA AÇÃO RECOMENDADA ====================

export function ProximaAcaoWidget({
  prazos,
  solicitacoes,
  canSeeCRM,
}: {
  prazos: any[];
  solicitacoes: any;
  canSeeCRM: boolean;
}) {
  const nextAction = useMemo(() => {
    // 1) Prazo crítico/vencido
    const critical = [...prazos]
      .filter((d) => (d.dias_restantes ?? 99) <= 3)
      .sort((a, b) => (a.dias_restantes ?? 99) - (b.dias_restantes ?? 99))[0];

    if (critical) {
      const days = critical.dias_restantes ?? 0;
      return {
        tone: "danger" as const,
        icon: AlertTriangle,
        eyebrow:
          days < 0
            ? "Prazo vencido"
            : days === 0
              ? "Prazo vence hoje"
              : `Prazo crítico · ${days} dia(s)`,
        title: critical.titulo || "Prazo sem título",
        desc: critical.case_title
          ? `${critical.case_title} — vence ${fmtDate(critical.data_prazo)}`
          : `Vence ${fmtDate(critical.data_prazo)}`,
        cta: "Ver e confirmar",
        to: "/atividades?tipo=prazo",
      };
    }

    // 2) Cliente aguardando
    if (canSeeCRM && Number(solicitacoes?.pendentes ?? 0) > 0) {
      const pending = Number(solicitacoes?.pendentes ?? 0);
      const late = Number(solicitacoes?.atrasadas ?? 0);
      return {
        tone: "warning" as const,
        icon: MessageSquare,
        eyebrow: late > 0 ? `${late} atrasada(s)` : "Cliente aguardando",
        title: `${pending} solicitação(ões) pendente(s)`,
        desc: late > 0
          ? "Responda na linha do tempo prioritária"
          : "Responda e registre o atendimento",
        cta: "Responder",
        to: solicitacoes?.destaque?.client_id
          ? `/clientes/${solicitacoes.destaque.client_id}?tab=atendimentos`
          : "/atividades?tab=relacionamento",
      };
    }

    return null;
  }, [prazos, solicitacoes, canSeeCRM]);

  if (!nextAction) {
    return (
      <BentoGridCell variant="highlight">
        <BentoGridHeader
          eyebrow="Status"
          title="Dia tranquilo"
          subtitle="Aproveite para tarefas estratégicas"
        />
        <BentoGridContent>
          <div className="flex items-center gap-3 rounded-lg bg-success-50 p-4 dark:bg-success-900/20">
            <Sparkles className="h-6 w-6 text-success-600 dark:text-success-400" />
            <div>
              <p className="text-sm font-medium text-success-800 dark:text-success-300">
                Sem urgências detectadas
              </p>
              <p className="mt-0.5 text-xs text-success-600 dark:text-success-400">
                Bom momento para revisão de casos ou estudos.
              </p>
            </div>
          </div>
        </BentoGridContent>
      </BentoGridCell>
    );
  }

  const ActionIcon = nextAction.icon;

  return (
    <BentoGridCell variant={nextAction.tone} colSpan={2}>
      <BentoGridHeader
        eyebrow={nextAction.eyebrow}
        title={nextAction.title}
        subtitle={nextAction.desc}
      />
      <BentoGridContent>
        <div className="flex items-start gap-3 rounded-lg bg-white/60 p-4 dark:bg-slate-800/60">
          <div className={cn(
            "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
            nextAction.tone === "danger" 
              ? "bg-danger-100 text-danger-600 dark:bg-danger-900/40 dark:text-danger-400"
              : "bg-warn-100 text-warn-600 dark:bg-warn-900/40 dark:text-warn-400",
          )}>
            <ActionIcon className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
              {nextAction.title}
            </p>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {nextAction.desc}
            </p>
          </div>
        </div>
      </BentoGridContent>
      <BentoGridFooter>
        <Button size="sm" variant={nextAction.tone === "danger" ? "danger" : "secondary"} asChild>
          <Link to={nextAction.to}>{nextAction.cta}</Link>
        </Button>
      </BentoGridFooter>
    </BentoGridCell>
  );
}

// ==================== WIDGET: CARTEIRA DE CASOS ====================

export function CarteiraCasosWidget({ casos }: { casos: any[] }) {
  const fases = useMemo(() => {
    const INACTIVE_CASE_STATUSES = new Set([
      "arquivado",
      "encerrado",
      "cancelado",
      "inativo",
    ]);

    const totals = new Map<string, number>();
    for (const item of casos) {
      const status = String(item.status || "").toLowerCase();
      if (item.archived_at || INACTIVE_CASE_STATUSES.has(status)) continue;
      const fase = String(item.fase || "sem fase").toLowerCase();
      totals.set(fase, (totals.get(fase) || 0) + 1);
    }
    return Array.from(totals.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([label, value]) => ({ label, value }));
  }, [casos]);

  const totalAtivos = fases.reduce((sum, f) => sum + f.value, 0);

  return (
    <BentoGridCell variant="default" rowSpan={fases.length > 3 ? 2 : 1}>
      <BentoGridHeader
        eyebrow="Visão geral"
        title="Carteira de casos"
        subtitle={`${totalAtivos} caso(s) ativo(s)`}
        action={
          <Link to="/casos">
            <Button variant="ghost" size="sm">
              Ver todos
            </Button>
          </Link>
        }
      />
      <BentoGridContent>
        {fases.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-sm text-slate-400">
            Nenhum caso ativo
          </div>
        ) : (
          <div className="space-y-3">
            {fases.map((fase, idx) => (
              <div key={fase.label} className="flex items-center gap-3">
                <div
                  className={cn(
                    "h-2 w-2 rounded-full",
                    idx === 0
                      ? "bg-danger-500"
                      : idx === 1
                        ? "bg-warn-500"
                        : "bg-primary-500",
                  )}
                />
                <span className="flex-1 truncate text-sm text-slate-700 dark:text-slate-300">
                  {fase.label.charAt(0).toUpperCase() + fase.label.slice(1)}
                </span>
                <Badge tone="amber">{fase.value}</Badge>
              </div>
            ))}
          </div>
        )}
      </BentoGridContent>
      <BentoGridFooter>
        <Link
          to="/kanban"
          className="text-xs font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400"
        >
          Abrir quadro Kanban →
        </Link>
      </BentoGridFooter>
    </BentoGridCell>
  );
}

// ==================== WIDGET: IA & AUTOMAÇÃO ====================

export function IAAutomacaoWidget({ iaSaude }: { iaSaude: any }) {
  const stats = useMemo(() => {
    if (!iaSaude) return null;

    return {
      total: iaSaude.total_solicitacoes ?? 0,
      aprovadas: iaSaude.aprovadas ?? 0,
      revisao: iaSaude.em_revisao ?? 0,
      economia: iaSaude.economia_horas ?? 0,
    };
  }, [iaSaude]);

  if (!stats) {
    return (
      <BentoGridCell variant="default">
        <BentoGridHeader
          eyebrow="Inteligência Artificial"
          title="IA & Automação"
          subtitle="Status não disponível"
        />
        <BentoGridContent>
          <div className="flex h-24 items-center justify-center">
            <SkeletonCard lines={2} header={false} />
          </div>
        </BentoGridContent>
      </BentoGridCell>
    );
  }

  const taxaAprovacao = stats.total > 0 
    ? Math.round((stats.aprovadas / stats.total) * 100) 
    : 0;

  return (
    <BentoGridCell variant="highlight">
      <BentoGridHeader
        eyebrow="Produtividade"
        title="IA & Automação"
        subtitle={`Economia de ${stats.economia}h este mês`}
        action={
          <Link to="/governanca-ia">
            <Button variant="ghost" size="sm" icon={<Bot className="h-3.5 w-3.5" />} />
          </Link>
        }
      />
      <BentoGridContent>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg bg-primary-50 p-3 dark:bg-primary-900/20">
            <p className="text-[10px] font-medium uppercase tracking-wide text-primary-600 dark:text-primary-400">
              Solicitações
            </p>
            <p className="mt-1 text-2xl font-bold text-primary-900 dark:text-primary-100">
              {stats.total}
            </p>
          </div>
          <div className="rounded-lg bg-success-50 p-3 dark:bg-success-900/20">
            <p className="text-[10px] font-medium uppercase tracking-wide text-success-600 dark:text-success-400">
              Taxa aprovação
            </p>
            <p className="mt-1 text-2xl font-bold text-success-900 dark:text-success-100">
              {taxaAprovacao}%
            </p>
          </div>
          <div className="rounded-lg bg-warn-50 p-3 dark:bg-warn-900/20">
            <p className="text-[10px] font-medium uppercase tracking-wide text-warn-600 dark:text-warn-400">
              Em revisão
            </p>
            <p className="mt-1 text-xl font-bold text-warn-900 dark:text-warn-100">
              {stats.revisao}
            </p>
          </div>
          <div className="rounded-lg bg-ouro-palha/20 p-3 dark:bg-ouro/10">
            <p className="text-[10px] font-medium uppercase tracking-wide text-ouro-profundo dark:text-ouro-palha">
              Horas economizadas
            </p>
            <p className="mt-1 text-xl font-bold text-ouro-profundo dark:text-ouro-palha">
              {stats.economia}h
            </p>
          </div>
        </div>
      </BentoGridContent>
      <BentoGridFooter>
        <Link
          to="/dashboard-ia"
          className="text-xs font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400"
        >
          Ver detalhes da IA →
        </Link>
      </BentoGridFooter>
    </BentoGridCell>
  );
}

// ==================== WIDGET: PRAZOS DA SEMANA ====================

export function PrazosSemanaWidget({ prazos }: { prazos: any[] }) {
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

  const max = Math.max(1, ...weeklySeries.map((p) => p.value));

  return (
    <BentoGridCell variant="default" colSpan={2}>
      <BentoGridHeader
        eyebrow="Planejamento"
        title="Prazos dos próximos 30 dias"
        subtitle={`${prazos.length} prazo(s) no total`}
      />
      <BentoGridContent>
        <div className="grid min-h-40 grid-cols-6 items-end gap-3 pt-2">
          {weeklySeries.map((point, index) => (
            <div key={point.label} className="flex h-full min-w-0 flex-col justify-end">
              <div className="mb-2 text-center text-xs font-semibold tabular-nums text-slate-700 dark:text-slate-200">
                {point.value}
              </div>
              <div className="flex h-32 items-end rounded-xl bg-slate-100/80 p-1.5 dark:bg-white/[0.05]">
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
      </BentoGridContent>
    </BentoGridCell>
  );
}

// ==================== WIDGET: ÁREAS DE ATUAÇÃO ====================

export function AreasAtuacaoWidget({ casos }: { casos: any[] }) {
  const areas = useMemo(() => {
    const totals = new Map<string, number>();
    for (const item of casos) {
      const area = String(item.area || "outros").toLowerCase();
      totals.set(area, (totals.get(area) || 0) + 1);
    }
    return Array.from(totals.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([label, value]) => ({ label, value }));
  }, [casos]);

  const AREA_TONES: Record<string, string> = {
    civil: "bg-primary-500",
    trabalhista: "bg-ai-500",
    consumidor: "bg-warn-500",
    familia: "bg-primary-300",
    ambiental: "bg-success-500",
    criminal: "bg-danger-500",
    previdenciario: "bg-warn-600",
    empresarial: "bg-primary-700",
    tributario: "bg-info-600",
  };

  return (
    <BentoGridCell variant="default">
      <BentoGridHeader
        eyebrow="Distribuição"
        title="Áreas de atuação"
        subtitle="Por volume de casos"
      />
      <BentoGridContent>
        {areas.length === 0 ? (
          <div className="flex h-24 items-center justify-center text-sm text-slate-400">
            Sem dados
          </div>
        ) : (
          <div className="space-y-3">
            {areas.map((area) => (
              <div key={area.label} className="flex items-center gap-3">
                <div
                  className={cn(
                    "h-2 w-2 rounded-full",
                    AREA_TONES[area.label] || "bg-slate-400",
                  )}
                />
                <span className="flex-1 capitalize text-sm text-slate-700 dark:text-slate-300">
                  {area.label}
                </span>
                <Badge tone="slate">{area.value}</Badge>
              </div>
            ))}
          </div>
        )}
      </BentoGridContent>
      <BentoGridFooter>
        <Link
          to="/ramos"
          className="text-xs font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400"
        >
          Gerenciar áreas →
        </Link>
      </BentoGridFooter>
    </BentoGridCell>
  );
}

// ==================== WIDGET: JURIMETRIA ====================

export function JurimetriaWidget({ jurimetria }: { jurimetria: any }) {
  const successRate =
    jurimetria?.taxa_sucesso_geral != null
      ? Math.round(jurimetria.taxa_sucesso_geral * 100)
      : null;

  if (!successRate) {
    return (
      <BentoGridCell variant="default">
        <BentoGridHeader
          eyebrow="Analytics"
          title="Jurimetria"
          subtitle="Dados insuficientes"
        />
        <BentoGridContent>
          <div className="flex h-24 items-center justify-center">
            <p className="text-sm text-slate-400">
              Necessário mais casos para análise
            </p>
          </div>
        </BentoGridContent>
      </BentoGridCell>
    );
  }

  return (
    <BentoGridCell variant="highlight">
      <BentoGridHeader
        eyebrow="Performance"
        title="Taxa de sucesso"
        subtitle="Baseado em casos encerrados"
        action={
          <Link to="/jurimetria">
            <Button variant="ghost" size="sm" icon={<BarChart3 className="h-3.5 w-3.5" />} />
          </Link>
        }
      />
      <BentoGridContent>
        <div className="flex h-32 flex-col items-center justify-center">
          <div className="relative flex h-24 w-24 items-center justify-center">
            <svg className="h-24 w-24 -rotate-90">
              <circle
                cx="48"
                cy="48"
                r="40"
                className="fill-none stroke-slate-200 dark:stroke-slate-700"
                strokeWidth="12"
              />
              <circle
                cx="48"
                cy="48"
                r="40"
                className="fill-none stroke-ouro"
                strokeWidth="12"
                strokeDasharray={`${(successRate / 100) * 251.2} 251.2`}
                strokeLinecap="round"
              />
            </svg>
            <div className="absolute text-center">
              <p className="text-2xl font-bold text-slate-900 dark:text-slate-100">
                {successRate}%
              </p>
            </div>
          </div>
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            Casos com êxito favorável
          </p>
        </div>
      </BentoGridContent>
      <BentoGridFooter>
        <Link
          to="/jurimetria"
          className="text-xs font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400"
        >
          Ver análise completa →
        </Link>
      </BentoGridFooter>
    </BentoGridCell>
  );
}

// ==================== WIDGET: MOVIMENTAÇÕES RECENTES ====================

export function MovimentacoesRecentesWidget({ movimentos }: { movimentos: any[] }) {
  const recent = movimentos.slice(0, 5);

  return (
    <BentoGridCell variant="default" rowSpan={recent.length > 3 ? 2 : 1}>
      <BentoGridHeader
        eyebrow="Acompanhamento"
        title="Movimentações recentes"
        subtitle="Últimas atualizações processuais"
        action={
          <Link to="/intimacoes">
            <Button variant="ghost" size="sm">
              Ver todas
            </Button>
          </Link>
        }
      />
      <BentoGridContent>
        {recent.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-sm text-slate-400">
            Nenhuma movimentação recente
          </div>
        ) : (
          <div className="space-y-3">
            {recent.map((mov, idx) => (
              <div key={idx} className="flex items-start gap-3">
                <div className="mt-1 h-2 w-2 shrink-0 rounded-full bg-primary-500" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-700 dark:text-slate-300">
                    {mov.descricao || "Movimentação sem descrição"}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-slate-400">
                    {mov.case_title || "Caso não identificado"}
                  </p>
                  <p className="mt-1 text-[10px] text-slate-400">
                    {fmtDate(mov.data_movimento)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </BentoGridContent>
      <BentoGridFooter>
        <Link
          to="/intimacoes"
          className="text-xs font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400"
        >
          Ver todas as intimações →
        </Link>
      </BentoGridFooter>
    </BentoGridCell>
  );
}

// ==================== SKELETON PARA CARREGAMENTO ====================

export function DashboardSkeleton() {
  return (
    <BentoGrid className="animate-pulse">
      <BentoGridCell colSpan={2}>
        <SkeletonCard lines={3} />
      </BentoGridCell>
      <BentoGridCell>
        <SkeletonCard lines={2} />
      </BentoGridCell>
      <BentoGridCell>
        <SkeletonCard lines={2} />
      </BentoGridCell>
      <BentoGridCell colSpan={2}>
        <SkeletonCard lines={4} />
      </BentoGridCell>
      <BentoGridCell rowSpan={2}>
        <SkeletonCard lines={5} />
      </BentoGridCell>
      <BentoGridCell>
        <SkeletonCard lines={3} />
      </BentoGridCell>
    </BentoGrid>
  );
}
