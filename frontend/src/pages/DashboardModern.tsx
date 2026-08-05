import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  BriefcaseBusiness,
  CalendarClock,
  CalendarDays,
  CheckSquare2,
  Clock3,
  FilePlus2,
  FileText,
  FolderOpen,
  Gavel,
  LayoutDashboard,
  ListChecks,
  Scale,
  Sparkles,
  UserPlus,
  Users,
  type LucideIcon,
} from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { useAuth } from "../stores/auth";
import { NOVO_CASO_DOCUMENTO_PATH } from "../lib/novoCaso";

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

const CLOSED_CASE_STATUSES = new Set(["encerrado", "arquivado"]);
const STATUS_COLORS = ["#b18a24", "#243047", "#768399", "#d7dee8"];

function safeNumber(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function parseDate(value?: string) {
  if (!value) return null;
  const normalized = value.includes("T") ? value : `${value}T12:00:00`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDateTime(value?: string) {
  const date = parseDate(value);
  return date
    ? new Intl.DateTimeFormat("pt-BR", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date)
    : "Horário não informado";
}

function formatToday() {
  const value = new Intl.DateTimeFormat("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(new Date());
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function humanize(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

type KpiCardProps = {
  label: string;
  value: number | string;
  meta: string;
  icon: LucideIcon;
  to: string;
  gold?: boolean;
};

function KpiCard({ label, value, meta, icon: Icon, to, gold }: KpiCardProps) {
  return (
    <Link to={to} className={`ejc-kpi-card${gold ? " is-gold" : ""}`}>
      <div className="ejc-kpi-head">
        <span className="ejc-kpi-label">{label}</span>
        <span className="ejc-kpi-icon">
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
      </div>
      <div className="ejc-kpi-value">{value}</div>
      <div className="ejc-kpi-meta">{meta}</div>
    </Link>
  );
}

type DashboardCardProps = {
  title: string;
  subtitle: string;
  to?: string;
  children: ReactNode;
};

function DashboardCard({ title, subtitle, to, children }: DashboardCardProps) {
  return (
    <section className="ejc-dashboard-card">
      <header className="ejc-dashboard-card-header">
        <span>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </span>
        {to && (
          <Link to={to} className="ejc-dashboard-card-link">
            Ver todos
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        )}
      </header>
      <div className="ejc-dashboard-card-body">{children}</div>
    </section>
  );
}

function LoadingRows({ count = 4 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="ejc-dashboard-skeleton" />
      ))}
    </div>
  );
}

export default function DashboardModern() {
  const { user } = useAuth();
  const [dashboard, setDashboard] = useState<any>(null);
  const [deadlines, setDeadlines] = useState<any[]>([]);
  const [movements, setMovements] = useState<any[]>([]);
  const [cases, setCases] = useState<any[]>([]);
  const [tasks, setTasks] = useState<any[]>([]);
  const [agendaEvents, setAgendaEvents] = useState<any[]>([]);
  const [failures, setFailures] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  const role = user?.role || "";
  const canCreateCase = CASE_CREATOR_ROLES.has(role);
  const canUseLegalAI = LEGAL_ROLES.has(role);
  const firstName = user?.full_name?.split(" ")[0] || "Doutor(a)";

  useEffect(() => {
    let active = true;
    setLoading(true);

    Promise.allSettled([
      api.get("/dashboard/"),
      api.get("/deadlines/?status=pendente&page_size=100"),
      api.get("/movimentos/recentes?limit=6"),
      api.get("/cases/?page_size=200"),
      api.get("/tasks/"),
      api.get("/agenda-eventos/?page_size=200"),
    ]).then((results) => {
      if (!active) return;
      const [dash, deadlineReq, movementReq, caseReq, taskReq, agendaReq] =
        results;
      const nextFailures: string[] = [];

      if (dash.status === "fulfilled") setDashboard(dash.value.data);
      else nextFailures.push("indicadores");

      if (deadlineReq.status === "fulfilled")
        setDeadlines(asList(deadlineReq.value.data));
      else nextFailures.push("prazos");

      if (movementReq.status === "fulfilled")
        setMovements(asList(movementReq.value.data));
      else nextFailures.push("andamentos");

      if (caseReq.status === "fulfilled") setCases(asList(caseReq.value.data));
      else nextFailures.push("processos");

      if (taskReq.status === "fulfilled") setTasks(asList(taskReq.value.data));
      else nextFailures.push("tarefas");

      if (agendaReq.status === "fulfilled")
        setAgendaEvents(asList(agendaReq.value.data));
      else nextFailures.push("agenda");

      setFailures(nextFailures);
      setLoading(false);
    });

    return () => {
      active = false;
    };
  }, []);

  const dashboardDegraded = new Set<string>(dashboard?.degradado ?? []);
  const casesUnavailable = failures.includes("processos");
  const taskUnavailable = failures.includes("tarefas");
  const deadlineUnavailable = failures.includes("prazos");

  const totalCases = !casesUnavailable
    ? cases.length
    : dashboardDegraded.has("casos")
      ? "—"
      : safeNumber(dashboard?.casos?.total);

  const activeCases = !casesUnavailable
    ? cases.filter((item) => {
        const status = String(item.status || "").toLowerCase();
        return !item.archived_at && !CLOSED_CASE_STATUSES.has(status);
      }).length
    : dashboardDegraded.has("casos")
      ? "—"
      : safeNumber(dashboard?.casos?.ativos);

  const pendingTasks = taskUnavailable
    ? "—"
    : tasks.filter((task) => task.status !== "concluida").length;

  const nextDeadlines = deadlineUnavailable
    ? "—"
    : deadlines.filter((deadline) => {
        const days = safeNumber(deadline.dias_restantes);
        return days >= 0 && days <= 7;
      }).length;

  const areas = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of cases) {
      const area = String(item.area || "Outros").trim() || "Outros";
      counts.set(area, (counts.get(area) || 0) + 1);
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 7)
      .map(([label, value]) => ({ label, value }));
  }, [cases]);

  const statuses = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of cases) {
      const status = String(item.status || "sem status").trim() || "sem status";
      counts.set(status, (counts.get(status) || 0) + 1);
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4)
      .map(([label, value], index) => ({
        label,
        value,
        color: STATUS_COLORS[index],
      }));
  }, [cases]);

  const statusTotal = statuses.reduce((sum, item) => sum + item.value, 0);
  const donutGradient = useMemo(() => {
    if (!statusTotal) return "conic-gradient(#e5e9ef 0deg 360deg)";
    let current = 0;
    const stops = statuses.map((item) => {
      const start = current;
      const portion = (item.value / statusTotal) * 360;
      current += portion;
      return `${item.color} ${start}deg ${current}deg`;
    });
    return `conic-gradient(${stops.join(", ")})`;
  }, [statuses, statusTotal]);

  const upcomingAgenda = useMemo(() => {
    const deadlineItems = deadlines.map((item) => ({
      id: `deadline-${item.id}`,
      type: "Prazo",
      title: item.titulo || "Prazo sem título",
      caseTitle: item.case_title,
      date: item.data_prazo,
      time: "Prazo",
      to: "/atividades?tipo=prazo",
      urgent: safeNumber(item.dias_restantes) <= 3,
    }));
    const eventItems = agendaEvents
      .filter((item) => !item.concluido)
      .map((item) => ({
        id: `agenda-${item.id}`,
        type: humanize(String(item.tipo || "Compromisso")),
        title: item.titulo || "Compromisso",
        caseTitle: item.caso_titulo,
        date: item.data_evento,
        time: item.hora || "Sem horário",
        to: "/atividades",
        urgent: false,
      }));

    return [...deadlineItems, ...eventItems]
      .filter((item) => parseDate(item.date))
      .sort(
        (a, b) =>
          (parseDate(a.date)?.getTime() ?? 0) -
          (parseDate(b.date)?.getTime() ?? 0),
      )
      .slice(0, 6);
  }, [deadlines, agendaEvents]);

  const quickActions: Array<{
    to: string;
    label: string;
    description: string;
    icon: LucideIcon;
  }> = [
    ...(canCreateCase
      ? [
          {
            to: NOVO_CASO_DOCUMENTO_PATH,
            label: "Novo processo",
            description: "Abrir por documento",
            icon: FilePlus2,
          },
          {
            to: "/clientes",
            label: "Novo cliente",
            description: "Cadastrar atendimento",
            icon: UserPlus,
          },
        ]
      : []),
    {
      to: "/atividades",
      label: "Agenda e prazos",
      description: "Organizar o dia",
      icon: CalendarDays,
    },
    {
      to: "/tarefas",
      label: "Nova tarefa",
      description: "Distribuir providência",
      icon: CheckSquare2,
    },
    ...(canUseLegalAI
      ? [
          {
            to: "/pecas",
            label: "Peças e modelos",
            description: "Produção jurídica",
            icon: FileText,
          },
          {
            to: "/inteligencia?tab=assistente",
            label: "IA jurídica",
            description: "Abrir assistente",
            icon: Bot,
          },
        ]
      : []),
  ].slice(0, 6);

  return (
    <div className="ejc-dashboard-v2 space-y-5">
      <div className="ejc-dashboard-titlebar">
        <div>
          <div className="ejc-dashboard-eyebrow">Painel do advogado</div>
          <h1>Bom trabalho, {firstName}</h1>
          <p>
            Visão objetiva dos processos, prazos, tarefas e compromissos do
            escritório.
          </p>
        </div>
        <div className="ejc-dashboard-date-pill">
          <CalendarClock className="h-4 w-4" aria-hidden="true" />
          {formatToday()}
        </div>
      </div>

      {failures.length > 0 && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            Alguns blocos estão temporariamente indisponíveis:{" "}
            {failures.join(", ")}. Os demais dados continuam sendo exibidos
            normalmente.
          </span>
        </div>
      )}

      <div className="ejc-dashboard-kpis">
        <KpiCard
          label="Total de processos"
          value={loading ? "—" : totalCases}
          meta="Carteira cadastrada no EJC"
          icon={BriefcaseBusiness}
          to="/casos"
        />
        <KpiCard
          label="Processos ativos"
          value={loading ? "—" : activeCases}
          meta="Em acompanhamento pelo escritório"
          icon={Scale}
          to="/casos?status=ativo"
          gold
        />
        <KpiCard
          label="Tarefas pendentes"
          value={loading ? "—" : pendingTasks}
          meta="Providências ainda não concluídas"
          icon={ListChecks}
          to="/tarefas"
        />
        <KpiCard
          label="Prazos próximos"
          value={loading ? "—" : nextDeadlines}
          meta="Vencimentos previstos em até 7 dias"
          icon={Clock3}
          to="/atividades?tipo=prazo"
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.45fr_0.85fr]">
        <DashboardCard
          title="Andamentos recentes"
          subtitle="Últimas movimentações dos processos acessíveis ao seu perfil"
          to="/casos"
        >
          {loading ? (
            <LoadingRows count={5} />
          ) : movements.length === 0 ? (
            <div className="ejc-dashboard-empty">
              <FolderOpen className="h-7 w-7" />
              Nenhum andamento recente disponível.
            </div>
          ) : (
            <div>
              {movements.slice(0, 6).map((movement, index) => (
                <Link
                  key={movement.id ?? index}
                  to={
                    movement.case_id ? `/casos/${movement.case_id}` : "/casos"
                  }
                  className="ejc-dashboard-feed-item"
                >
                  <span className="ejc-dashboard-feed-dot">
                    <Gavel className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="ejc-dashboard-feed-title">
                      {movement.descricao ||
                        humanize(movement.tipo || "Andamento")}
                    </span>
                    <span className="ejc-dashboard-feed-meta">
                      <span>{movement.case_titulo || "Processo"}</span>
                      {movement.numero_interno && (
                        <span>• {movement.numero_interno}</span>
                      )}
                      <span>• {formatDateTime(movement.quando)}</span>
                    </span>
                  </span>
                  <ArrowRight className="mt-2 h-3.5 w-3.5 shrink-0 text-slate-400" />
                </Link>
              ))}
            </div>
          )}
        </DashboardCard>

        <DashboardCard
          title="Agenda da semana"
          subtitle="Prazos e compromissos em ordem cronológica"
          to="/atividades"
        >
          {loading ? (
            <LoadingRows count={5} />
          ) : upcomingAgenda.length === 0 ? (
            <div className="ejc-dashboard-empty">
              <CalendarDays className="h-7 w-7" />
              Nenhum compromisso próximo encontrado.
            </div>
          ) : (
            <div>
              {upcomingAgenda.map((item) => {
                const date = parseDate(item.date);
                return (
                  <Link key={item.id} to={item.to} className="ejc-agenda-row">
                    <span className="ejc-agenda-date">
                      <strong>{date?.getDate() ?? "--"}</strong>
                      <small>
                        {date
                          ? new Intl.DateTimeFormat("pt-BR", {
                              month: "short",
                            }).format(date)
                          : "data"}
                      </small>
                    </span>
                    <span className="min-w-0">
                      <span className="ejc-dashboard-feed-title">
                        {item.title}
                      </span>
                      <span className="ejc-dashboard-feed-meta">
                        <span>{item.type}</span>
                        {item.caseTitle && <span>• {item.caseTitle}</span>}
                      </span>
                    </span>
                    <span
                      className={`ejc-agenda-time${item.urgent ? " text-red-600 dark:text-red-300" : ""}`}
                    >
                      {item.time}
                    </span>
                  </Link>
                );
              })}
            </div>
          )}
        </DashboardCard>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_0.95fr_1.05fr]">
        <DashboardCard
          title="Distribuição por área"
          subtitle="Processos agrupados por área de atuação"
        >
          {loading ? (
            <LoadingRows count={5} />
          ) : areas.length === 0 ? (
            <div className="ejc-dashboard-empty">
              <LayoutDashboard className="h-7 w-7" />
              Sem dados suficientes para distribuição.
            </div>
          ) : (
            <div>
              {areas.map((area) => (
                <div key={area.label} className="ejc-area-row">
                  <span className="ejc-area-label">{area.label}</span>
                  <span className="ejc-area-track">
                    <span
                      className="ejc-area-fill block"
                      style={{
                        width: `${Math.max(8, (area.value / Math.max(...areas.map((item) => item.value))) * 100)}%`,
                      }}
                    />
                  </span>
                  <span className="ejc-area-value">{area.value}</span>
                </div>
              ))}
            </div>
          )}
        </DashboardCard>

        <DashboardCard
          title="Processos por status"
          subtitle="Composição atual da carteira"
        >
          {loading ? (
            <LoadingRows count={4} />
          ) : statusTotal === 0 ? (
            <div className="ejc-dashboard-empty">
              <BriefcaseBusiness className="h-7 w-7" />
              Nenhum processo disponível para o gráfico.
            </div>
          ) : (
            <div className="ejc-status-layout">
              <div className="relative">
                <div
                  className="ejc-status-donut"
                  style={{ background: donutGradient }}
                  aria-label={`${statusTotal} processos distribuídos por status`}
                />
                <div className="ejc-status-donut-label">
                  <strong>{statusTotal}</strong>
                  <small>processos</small>
                </div>
              </div>
              <div className="ejc-status-legend">
                {statuses.map((status) => (
                  <div key={status.label} className="ejc-status-legend-row">
                    <i style={{ background: status.color }} />
                    <span>{humanize(status.label)}</span>
                    <strong>{status.value}</strong>
                  </div>
                ))}
              </div>
            </div>
          )}
        </DashboardCard>

        <DashboardCard
          title="Atalhos rápidos"
          subtitle="Ações mais usadas no fluxo jurídico"
        >
          <div className="ejc-quick-actions">
            {quickActions.map(({ to, label, description, icon: Icon }) => (
              <Link key={`${to}-${label}`} to={to} className="ejc-quick-action">
                <span className="ejc-quick-action-icon">
                  <Icon className="h-4 w-4" />
                </span>
                <span className="min-w-0">
                  <strong>{label}</strong>
                  <small>{description}</small>
                </span>
              </Link>
            ))}
          </div>
          {canUseLegalAI && (
            <Link
              to="/raio-x"
              className="mt-3 flex items-center justify-between rounded-xl border border-violet-200 bg-violet-50 px-4 py-3 text-xs font-semibold text-violet-800 transition hover:bg-violet-100 dark:border-violet-500/20 dark:bg-violet-500/10 dark:text-violet-200"
            >
              <span className="flex items-center gap-2">
                <Sparkles className="h-4 w-4" />
                Analisar documento antes de cadastrar
              </span>
              <ArrowRight className="h-4 w-4" />
            </Link>
          )}
        </DashboardCard>
      </div>

      <div className="rounded-xl border border-slate-200/80 bg-white/65 px-4 py-3 text-[10px] text-slate-500 dark:border-white/10 dark:bg-white/[0.025] dark:text-slate-400">
        <span className="inline-flex items-center gap-2">
          <Users className="h-3.5 w-3.5 text-[#92711a] dark:text-[#e5ce7f]" />
          Este dashboard é compartilhado pela equipe jurídica e não apresenta
          informações financeiras.
        </span>
      </div>
    </div>
  );
}
