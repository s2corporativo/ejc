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
  Clock,
  DollarSign,
  FileText,
  FolderOpen,
  Gavel,
  Plus,
  Scale,
  ShieldCheck,
  Sparkles,
  Users,
  Wallet,
} from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { useAuth } from "../stores/auth";
import NoticiasCard from "../components/NoticiasCard";
import ThemeSelector from "../components/ThemeSelector";
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
  fmtMoney,
} from "../components/UI";

const FINANCE_ROLES = new Set(["superadmin", "admin", "socio", "financeiro"]);

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

const AREA_BARS = [
  "bg-primary-700",
  "bg-primary-500",
  "bg-primary-300",
  "bg-ai-500",
  "bg-success-500",
  "bg-warn-500",
];

function initials(value?: string) {
  return (value || "?")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function WeeklyDeadlineChart({
  points,
}: {
  points: Array<{ label: string; value: number }>;
}) {
  const max = Math.max(1, ...points.map((point) => point.value));

  return (
    <div className="grid min-h-52 grid-cols-6 items-end gap-3 pt-5">
      {points.map((point, index) => {
        const height = Math.max(10, Math.round((point.value / max) * 150));
        const critical = index === 0 && point.value > 0;
        return (
          <div key={point.label} className="flex h-full min-w-0 flex-col justify-end">
            <div className="mb-2 text-center text-xs font-semibold tabular-nums text-slate-700 dark:text-slate-200">
              {point.value}
            </div>
            <div className="flex h-40 items-end rounded-xl bg-slate-100/80 p-1.5 dark:bg-white/[0.05]">
              <div
                className={cn(
                  "w-full rounded-lg transition-all duration-300",
                  critical
                    ? "bg-gradient-to-t from-danger-600 to-danger-400"
                    : "bg-gradient-to-t from-primary-800 via-primary-600 to-primary-400",
                )}
                style={{ height }}
                aria-label={`${point.label}: ${point.value} prazo(s)`}
              />
            </div>
            <div className="mt-2 truncate text-center text-[10px] font-medium text-slate-400">
              {point.label}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PortfolioDistribution({
  areas,
}: {
  areas: Array<{ label: string; value: number }>;
}) {
  const max = Math.max(1, ...areas.map((area) => area.value));

  if (areas.length === 0) {
    return <EmptyState title="Sem casos na carteira" icon={Briefcase} />;
  }

  return (
    <div className="space-y-3">
      {areas.map((area, index) => (
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
                "h-full rounded-full transition-all duration-300",
                AREA_BARS[index % AREA_BARS.length],
              )}
              style={{ width: `${Math.max(8, (area.value / max) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

export default function DashboardModern() {
  const { user } = useAuth();
  const [dashboard, setDashboard] = useState<any>(null);
  const [jurimetria, setJurimetria] = useState<any>(null);
  const [prazos, setPrazos] = useState<any[]>([]);
  const [movimentos, setMovimentos] = useState<any[]>([]);
  const [casos, setCasos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      api.get("/dashboard/"),
      api.get("/jurimetria/overview"),
      api.get("/deadlines/?status=pendente&page_size=100"),
      api.get("/movimentos/recentes?limit=8"),
      api.get("/cases/?page_size=200"),
    ])
      .then(([dash, juri, deadlines, movs, cases]) => {
        if (dash.status === "fulfilled") setDashboard(dash.value.data);
        if (juri.status === "fulfilled") setJurimetria(juri.value.data);
        if (deadlines.status === "fulfilled") {
          setPrazos(asList(deadlines.value.data));
        }
        if (movs.status === "fulfilled") setMovimentos(asList(movs.value.data));
        if (cases.status === "fulfilled") setCasos(asList(cases.value.data));
      })
      .finally(() => setLoading(false));
  }, []);

  const role = user?.role || "";
  const canSeeFinance = FINANCE_ROLES.has(role);
  const firstName = user?.full_name?.split(" ")[0] || "Dr.";

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
      const distance = Math.floor(
        (date.getTime() - today.getTime()) / (7 * 24 * 60 * 60 * 1000),
      );
      if (distance < 6) buckets[Math.max(0, distance)] += 1;
    }

    return buckets.map((value, index) => ({
      label: index === 0 ? "Esta sem." : `+${index} sem.",
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

  const successRate =
    jurimetria?.taxa_sucesso_geral != null
      ? Math.round(jurimetria.taxa_sucesso_geral * 100)
      : null;
  const pendingFees =
    dashboard?.financeiro?.pendente ??
    dashboard?.financeiro?.honorarios_pendentes;
  const monthlyRevenue =
    dashboard?.financeiro?.honorarios_mes ?? dashboard?.financeiro?.receita_mes;
  const received = typeof monthlyRevenue === "number" ? monthlyRevenue : 0;
  const pending = typeof pendingFees === "number" ? pendingFees : 0;
  const receivedPercentage =
    received + pending > 0 ? Math.round((received / (received + pending)) * 100) : 0;

  const quickActions = [
    { to: "/casos", label: "Novo caso", icon: Plus, primary: true },
    { to: "/clientes", label: "Novo cliente", icon: Users },
    { to: "/pecas", label: "Gerar peça", icon: FileText },
    { to: "/inteligencia", label: "Analisar com IA", icon: Sparkles },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Painel executivo"
        title={`Bom trabalho, ${firstName}`}
        subtitle="Visão consolidada da operação jurídica, com foco em prazos, carteira, produtividade e segurança decisória."
        actions={<ThemeSelector className="w-full sm:w-auto sm:min-w-[330px]" />}
      />

      <section className="overflow-hidden rounded-2xl border border-primary-800/20 bg-gradient-to-br from-primary-950 via-primary-900 to-primary-700 p-5 text-white shadow-lg dark:border-primary-300/20 dark:from-[#17100c] dark:via-[#261a13] dark:to-[#4a3427] md:p-6">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
          <div className="max-w-2xl">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge className="bg-white/10 text-primary-100 ring-white/15">
                Operação segura
              </Badge>
              <span className="inline-flex items-center gap-1.5 text-xs text-primary-100/80">
                <ShieldCheck className="h-3.5 w-3.5" />
                Auditoria e LGPD preservadas
              </span>
            </div>
            <h2 className="text-xl font-semibold text-white md:text-2xl">
              Decida o que precisa de atenção agora
            </h2>
            <p className="mt-2 text-sm leading-6 text-primary-100/80">
              O painel prioriza riscos, vencimentos e movimentações recentes sem substituir a validação profissional do advogado.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {quickActions.map(({ to, label, icon: Icon, primary }) => (
              <Link key={label} to={to}>
                <Button
                  variant={primary ? "secondary" : "ghost"}
                  icon={<Icon className="h-4 w-4" />}
                  className={cn(
                    primary
                      ? "border-white/20 bg-white text-primary-950 hover:bg-primary-50"
                      : "text-white hover:bg-white/10",
                  )}
                >
                  {label}
                </Button>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
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
        {canSeeFinance ? (
          <StatCard
            label="Receita do mês"
            value={typeof monthlyRevenue === "number" ? fmtMoney(monthlyRevenue) : "—"}
            subtitle="Honorários recebidos"
            icon={<DollarSign className="h-5 w-5" />}
            tone="green"
            trend={received > 0 ? "up" : undefined}
          />
        ) : (
          <StatCard
            label="Movimentações"
            value={movimentos.length}
            subtitle="Atividades recentes"
            icon={<Gavel className="h-5 w-5" />}
            tone="green"
          />
        )}
        <StatCard
          label={canSeeFinance ? "A receber" : "Taxa de êxito"}
          value={
            canSeeFinance
              ? typeof pendingFees === "number"
                ? fmtMoney(pendingFees)
                : "—"
              : successRate != null
                ? `${successRate}%`
                : "—"
          }
          subtitle={canSeeFinance ? "Honorários pendentes" : "Base jurimétrica disponível"}
          icon={
            canSeeFinance ? (
              <Wallet className="h-5 w-5" />
            ) : (
              <BarChart3 className="h-5 w-5" />
            )
          }
          tone="amber"
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <SectionCard
          title="Prazos das próximas semanas"
          subtitle="Distribuição temporal dos compromissos pendentes."
          actions={
            <Link to="/prazos" className="text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300">
              Ver prazos
            </Link>
          }
        >
          {loading ? (
            <div className="h-52 animate-pulse rounded-xl bg-slate-100 dark:bg-white/[0.05]" />
          ) : (
            <WeeklyDeadlineChart points={weeklySeries} />
          )}
        </SectionCard>

        <div className="space-y-5">
          <SectionCard title="Carteira por área" subtitle="Concentração dos casos cadastrados.">
            <PortfolioDistribution areas={areas} />
          </SectionCard>

          {canSeeFinance && (
            <SectionCard title="Honorários" subtitle="Recebido em relação ao total previsto.">
              <div className="flex items-end justify-between gap-3">
                <div className="text-2xl font-semibold tracking-tight text-slate-950 tabular-nums dark:text-slate-100">
                  {receivedPercentage}%
                </div>
                <div className="text-right text-xs text-slate-400">
                  {fmtMoney(received)} de {fmtMoney(received + pending)}
                </div>
              </div>
              <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-slate-100 dark:bg-white/[0.06]">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-success-500 to-primary-500 transition-all"
                  style={{ width: `${receivedPercentage}%` }}
                />
              </div>
              <div className="mt-3 flex items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                <CheckCircle2 className="h-3.5 w-3.5 text-success-600" />
                Indicador restrito aos perfis financeiros autorizados.
              </div>
            </SectionCard>
          )}
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
        <SectionCard
          title="Agenda e prazos próximos"
          subtitle="Itens ordenados por data para tratamento imediato."
          actions={
            <Link to="/atividades" className="text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300">
              Abrir central
            </Link>
          }
        >
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((item) => (
                <div key={item} className="h-16 animate-pulse rounded-xl bg-slate-100 dark:bg-white/[0.05]" />
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
                const tone = days <= 0 ? "red" : days <= 3 ? "amber" : "slate";
                return (
                  <Link
                    key={deadline.id ?? index}
                    to="/atividades"
                    className="flex items-center gap-4 rounded-xl px-2 py-3 transition-colors hover:bg-slate-50 dark:hover:bg-white/[0.04]"
                  >
                    <div className="flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-xl border border-slate-200 bg-white dark:border-white/10 dark:bg-white/[0.04]">
                      <span className="text-sm font-semibold text-slate-950 dark:text-slate-100">
                        {deadline.data_prazo ? new Date(deadline.data_prazo).getDate() : "--"}
                      </span>
                      <span className="text-[10px] uppercase text-slate-400">dia</span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold text-slate-950 dark:text-slate-100">
                        {deadline.titulo || "Prazo sem título"}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                        <Clock className="h-3.5 w-3.5" />
                        {fmtDate(deadline.data_prazo)}
                        {deadline.case_title && <span className="truncate">• {deadline.case_title}</span>}
                      </div>
                    </div>
                    <Badge tone={tone}>
                      {days < 0 ? "Vencido" : days === 0 ? "Hoje" : `${days} dias`}
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
          actions={<Sparkles className="h-4 w-4 text-ai-600 dark:text-ai-300" />}
        >
          <div className="space-y-3">
            <Link
              to="/prazos"
              className="block rounded-xl border border-danger-100 bg-danger-50 p-4 transition-colors hover:border-danger-200 dark:border-danger-500/20 dark:bg-danger-500/10"
            >
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-4 w-4 text-danger-600 dark:text-danger-300" />
                <div>
                  <div className="text-sm font-semibold text-danger-800 dark:text-danger-200">
                    {criticalDeadlines.length} prazo(s) crítico(s)
                  </div>
                  <p className="mt-1 text-xs text-danger-700 dark:text-danger-300/80">
                    Priorize vencimentos em até três dias e registre a providência adotada.
                  </p>
                </div>
              </div>
            </Link>

            <Link
              to="/inteligencia"
              className="block rounded-xl border border-ai-100 bg-ai-50 p-4 transition-colors hover:border-ai-200 dark:border-ai-500/20 dark:bg-ai-500/10"
            >
              <div className="flex items-start gap-3">
                <Bot className="mt-0.5 h-4 w-4 text-ai-700 dark:text-ai-300" />
                <div>
                  <div className="text-sm font-semibold text-ai-900 dark:text-ai-200">
                    IA jurídica assistiva
                  </div>
                  <p className="mt-1 text-xs text-ai-800 dark:text-ai-300/80">
                    Rascunhos e análises exigem conferência das fontes e revisão humana antes do uso.
                  </p>
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
                    A interface não amplia permissões: o backend continua sendo a fonte de verdade do RBAC.
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
            <Link to="/casos" className="text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300">
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
                  className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 transition-colors hover:border-primary-200 hover:bg-primary-50/40 dark:border-white/10 dark:bg-white/[0.03] dark:hover:border-primary-400/30 dark:hover:bg-white/[0.06]"
                >
                  <div
                    className={cn(
                      "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-xs font-semibold text-white",
                      AREA_TONES[String(item.area || "").toLowerCase()] || "bg-slate-700",
                    )}
                  >
                    {initials(item.titulo || item.numero_interno)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-semibold text-slate-950 dark:text-slate-100">
                      {item.titulo || item.numero_interno || "Caso sem título"}
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
            <Link to="/atividades" className="text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-300">
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
                  to={movement.case_id ? `/casos/${movement.case_id}` : "/atividades"}
                  className="flex items-start gap-3 rounded-xl border border-slate-100 bg-white p-3 transition-colors hover:bg-slate-50 dark:border-white/[0.07] dark:bg-white/[0.03] dark:hover:bg-white/[0.06]"
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

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <SectionCard title="Atalhos operacionais" subtitle="Fluxos frequentes e padronizados.">
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              { to: "/pecas", label: "Produção jurídica", icon: FileText },
              { to: "/documentos", label: "Gestão documental", icon: FolderOpen },
              { to: "/inteligencia", label: "IA do escritório", icon: Sparkles },
              { to: "/jurimetria", label: "Jurimetria", icon: Scale },
            ].map(({ to, label, icon: Icon }) => (
              <Link
                key={to}
                to={to}
                className="group flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 text-sm font-semibold text-slate-700 transition-all hover:border-primary-200 hover:bg-primary-50 dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-200 dark:hover:border-primary-400/30 dark:hover:bg-white/[0.06]"
              >
                <div className="rounded-lg bg-primary-50 p-2 text-primary-700 group-hover:bg-white dark:bg-primary-400/10 dark:text-primary-300 dark:group-hover:bg-white/[0.06]">
                  <Icon className="h-5 w-5" />
                </div>
                <span className="min-w-0 flex-1">{label}</span>
                <ArrowRight className="h-4 w-4 text-slate-400" />
              </Link>
            ))}
          </div>
        </SectionCard>

        <NoticiasCard />
      </div>
    </div>
  );
}
