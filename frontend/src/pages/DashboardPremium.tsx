import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ArrowRight,
  BriefcaseBusiness,
  CalendarClock,
  CheckSquare2,
  CircleGauge,
  Clock3,
  FilePlus2,
  FileText,
  FolderOpen,
  Gavel,
  Import,
  ListTodo,
  Plus,
  Scale,
  Sparkles,
  UserPlus,
  Users,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { asList } from "../lib/list";
import {
  NOVO_CASO_DOCUMENTO_PATH,
  NOVO_CASO_MANUAL_PATH,
} from "../lib/novoCaso";
import { useAuth } from "../stores/auth";
import { Badge, EmptyState, StatusBadge, cn } from "../components/UI";

interface DashboardPayload {
  casos?: {
    por_status?: Record<string, number>;
    por_area?: Array<{ area?: string; total?: number }>;
    total?: number;
    ativos?: number;
    arquivados?: number;
    encerrados?: number;
  };
  prazos?: {
    vencidos?: number;
    criticos_3d?: number;
    proximos_7d?: number;
  };
  degradado?: string[];
}

interface ActivityItem {
  id?: string;
  tipo?: string;
  subtipo?: string;
  fonte?: string;
  titulo?: string;
  descricao?: string;
  date?: string;
  status?: string;
  case_id?: string;
  caso_titulo?: string;
  hora?: string;
  local?: string;
}

interface AgendaEvent {
  id?: string;
  tipo?: string;
  hora?: string;
  local?: string;
}

interface MovementItem {
  id?: string;
  titulo?: string;
  descricao?: string;
  tipo?: string;
  status?: string;
  data?: string;
  created_at?: string;
  data_movimento?: string;
  case_id?: string;
  case_title?: string;
  case_number?: string;
  numero_processo?: string;
  cliente_nome?: string;
}

const FINAL_ACTIVITY_STATUSES = new Set([
  "concluido",
  "concluida",
  "tratada",
  "cancelado",
  "arquivado",
  "encerrado",
]);

const CREATE_CASE_ROLES = new Set([
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

const STATUS_COLORS = [
  "#c9a227",
  "#101923",
  "#8f7117",
  "#8b96a1",
  "#d7dbe0",
  "#e5ce7f",
];

function formatDateTime(value?: string) {
  if (!value) return "Data não informada";
  const parsed = new Date(value.includes("T") ? value : `${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return "Data não informada";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: value.includes("T") ? "2-digit" : undefined,
    minute: value.includes("T") ? "2-digit" : undefined,
  }).format(parsed);
}

function dateKey(value?: string) {
  return value?.slice(0, 10) ?? "";
}

function formatArea(value?: string) {
  if (!value) return "Outros";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isFinalActivity(status?: string) {
  return FINAL_ACTIVITY_STATUSES.has((status || "").toLowerCase());
}

function buildDonutGradient(entries: Array<{ value: number; color: string }>) {
  const total = entries.reduce((sum, entry) => sum + entry.value, 0);
  if (total <= 0) return "conic-gradient(#e5e7eb 0 100%)";
  let cursor = 0;
  const stops = entries.map((entry) => {
    const start = cursor;
    cursor += (entry.value / total) * 100;
    return `${entry.color} ${start.toFixed(2)}% ${cursor.toFixed(2)}%`;
  });
  return `conic-gradient(${stops.join(", ")})`;
}

function Panel({
  title,
  action,
  children,
  className,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("ejc-premium-panel", className)}>
      <header>
        <h2>{title}</h2>
        {action}
      </header>
      <div className="ejc-premium-panel__body">{children}</div>
    </section>
  );
}

function MetricCard({
  label,
  value,
  unavailable,
  loading,
  subtitle,
  icon: Icon,
  to,
  featured = false,
}: {
  label: string;
  value: number | null;
  unavailable: boolean;
  loading: boolean;
  subtitle: string;
  icon: LucideIcon;
  to: string;
  featured?: boolean;
}) {
  return (
    <Link
      to={to}
      className={cn(
        "ejc-premium-metric",
        featured && "is-featured",
        unavailable && "is-unavailable",
      )}
      aria-label={`${label}: ${
        loading ? "carregando" : unavailable ? "indisponível" : value
      }`}
    >
      <span className="ejc-premium-metric__icon">
        <Icon aria-hidden="true" />
      </span>
      <span className="ejc-premium-metric__content">
        <small>{label}</small>
        {loading ? (
          <i className="ejc-skeleton h-8 w-20" aria-label="Carregando" />
        ) : unavailable ? (
          <strong className="is-text">Indisponível</strong>
        ) : (
          <strong>{value ?? 0}</strong>
        )}
        <em>{unavailable ? "Falha na atualização" : subtitle}</em>
      </span>
      <ArrowRight className="ejc-premium-metric__arrow" aria-hidden="true" />
    </Link>
  );
}

export default function DashboardPremium() {
  const user = useAuth((state) => state.user);
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [agendaEvents, setAgendaEvents] = useState<AgendaEvent[]>([]);
  const [movements, setMovements] = useState<MovementItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState({
    dashboard: false,
    activities: false,
    agenda: false,
    movements: false,
  });

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.allSettled([
      api.get("/dashboard/"),
      api.get("/atividades", { params: { apenas_pendentes: false } }),
      api.get("/agenda-eventos/", { params: { page_size: 500 } }),
      api.get("/movimentos/recentes?limit=8"),
    ])
      .then(([dashboardResult, activitiesResult, agendaResult, movementResult]) => {
        if (!active) return;
        setFailed({
          dashboard: dashboardResult.status === "rejected",
          activities: activitiesResult.status === "rejected",
          agenda: agendaResult.status === "rejected",
          movements: movementResult.status === "rejected",
        });
        if (dashboardResult.status === "fulfilled") {
          setDashboard(dashboardResult.value.data);
        }
        if (activitiesResult.status === "fulfilled") {
          setActivities(asList(activitiesResult.value.data));
        }
        if (agendaResult.status === "fulfilled") {
          setAgendaEvents(asList(agendaResult.value.data));
        }
        if (movementResult.status === "fulfilled") {
          setMovements(asList(movementResult.value.data));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const degraded = new Set(dashboard?.degradado || []);
  const casesUnavailable = failed.dashboard || degraded.has("casos");
  const deadlinesUnavailable = failed.dashboard || degraded.has("prazos");
  const tasksUnavailable = failed.activities;

  const pendingTasks = useMemo(
    () =>
      activities.filter(
        (item) =>
          (item.tipo === "tarefa" || item.fonte === "tarefa") &&
          !isFinalActivity(item.status),
      ).length,
    [activities],
  );

  const agendaMap = useMemo(() => {
    const map = new Map<string, AgendaEvent>();
    for (const event of agendaEvents) {
      if (event.id) map.set(event.id, event);
    }
    return map;
  }, [agendaEvents]);

  const weeklyAgenda = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const day = today.getDay() || 7;
    const monday = new Date(today);
    monday.setDate(today.getDate() - day + 1);
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);
    sunday.setHours(23, 59, 59, 999);

    return activities
      .map((item) => {
        const event = item.id ? agendaMap.get(item.id) : undefined;
        return {
          ...item,
          hora: item.hora || event?.hora,
          local: item.local || event?.local,
          subtipo: item.subtipo || event?.tipo,
        };
      })
      .filter((item) => {
        if (!item.date) return false;
        const parsed = new Date(
          item.date.includes("T") ? item.date : `${item.date}T12:00:00`,
        );
        return parsed >= monday && parsed <= sunday;
      })
      .sort((a, b) =>
        `${a.date || ""} ${a.hora || ""}`.localeCompare(
          `${b.date || ""} ${b.hora || ""}`,
        ),
      )
      .slice(0, 6);
  }, [activities, agendaMap]);

  const areas = useMemo(
    () =>
      (dashboard?.casos?.por_area || [])
        .map((item) => ({
          label: formatArea(item.area),
          value: Number(item.total || 0),
        }))
        .filter((item) => item.value > 0)
        .sort((a, b) => b.value - a.value)
        .slice(0, 6),
    [dashboard],
  );

  const statusEntries = useMemo(
    () =>
      Object.entries(dashboard?.casos?.por_status || {})
        .map(([label, value], index) => ({
          label: formatArea(label),
          value: Number(value || 0),
          color: STATUS_COLORS[index % STATUS_COLORS.length],
        }))
        .filter((item) => item.value > 0)
        .sort((a, b) => b.value - a.value),
    [dashboard],
  );

  const donutGradient = useMemo(
    () => buildDonutGradient(statusEntries),
    [statusEntries],
  );
  const totalCases = Number(dashboard?.casos?.total || 0);
  const maxArea = Math.max(1, ...areas.map((item) => item.value));

  const canCreateCase = CREATE_CASE_ROLES.has(user?.role || "");
  const canUseLegal = LEGAL_ROLES.has(user?.role || "");
  const quickActions = [
    ...(canCreateCase
      ? [
          {
            to: NOVO_CASO_DOCUMENTO_PATH,
            label: "Novo processo por documento",
            icon: FilePlus2,
          },
          {
            to: NOVO_CASO_MANUAL_PATH,
            label: "Novo processo manual",
            icon: Plus,
          },
          { to: "/clientes", label: "Novo cliente", icon: UserPlus },
        ]
      : []),
    { to: "/atividades?view=calendario", label: "Agenda", icon: CalendarClock },
    { to: "/atividades?tipo=tarefa", label: "Nova tarefa", icon: ListTodo },
    ...(canUseLegal
      ? [
          { to: "/pecas", label: "Peças e modelos", icon: FileText },
          { to: "/entrada", label: "Importar documento", icon: Import },
          { to: "/inteligencia", label: "Iniciar caso com IA", icon: Sparkles },
        ]
      : []),
  ].slice(0, 7);

  const movementUnavailable = failed.movements;
  const agendaUnavailable = failed.activities;
  const firstName = user?.full_name?.split(" ")[0] || "colega";

  return (
    <div className="ejc-dashboard-premium space-y-5">
      <div className="ejc-dashboard-premium__intro">
        <div>
          <span>Visão operacional do escritório</span>
          <h1>Bom trabalho, {firstName}</h1>
          <p>
            Processos, prazos, atividades e movimentações provenientes das
            bases reais do EJC.
          </p>
        </div>
        <Badge tone="ouro">Dashboard sem dados financeiros</Badge>
      </div>

      <section
        className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-4"
        aria-label="Indicadores operacionais"
      >
        <MetricCard
          label="Total de Processos"
          value={dashboard?.casos?.total ?? null}
          unavailable={casesUnavailable}
          loading={loading}
          subtitle="Atualizado agora"
          icon={Scale}
          to="/casos"
        />
        <MetricCard
          label="Processos Ativos"
          value={dashboard?.casos?.ativos ?? null}
          unavailable={casesUnavailable}
          loading={loading}
          subtitle="Carteira em andamento"
          icon={FolderOpen}
          to="/casos?status=ativo"
          featured
        />
        <MetricCard
          label="Tarefas Pendentes"
          value={pendingTasks}
          unavailable={tasksUnavailable}
          loading={loading}
          subtitle="Ações ainda não concluídas"
          icon={CheckSquare2}
          to="/atividades?tipo=tarefa"
        />
        <MetricCard
          label="Prazos Próximos"
          value={dashboard?.prazos?.proximos_7d ?? null}
          unavailable={deadlinesUnavailable}
          loading={loading}
          subtitle="Próximos sete dias"
          icon={CalendarClock}
          to="/atividades?tipo=prazo"
        />
      </section>

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel
          title="Andamentos Recentes"
          action={
            <Link to="/casos" className="ejc-premium-panel__link">
              Ver todos
            </Link>
          }
        >
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((item) => (
                <div key={item} className="ejc-skeleton h-20 w-full" />
              ))}
            </div>
          ) : movementUnavailable ? (
            <EmptyState
              title="Andamentos indisponíveis"
              message="A fonte de movimentações não respondeu. Nenhum valor fictício foi exibido."
              icon={Gavel}
            />
          ) : movements.length === 0 ? (
            <EmptyState
              title="Nenhum andamento recente"
              message="Não há movimentações recentes disponíveis para este perfil."
              icon={Gavel}
            />
          ) : (
            <div className="ejc-premium-feed">
              {movements.slice(0, 6).map((movement, index) => {
                const title =
                  movement.titulo ||
                  movement.descricao ||
                  movement.tipo ||
                  "Andamento processual";
                const process =
                  movement.case_number ||
                  movement.numero_processo ||
                  movement.case_title;
                const when =
                  movement.data_movimento ||
                  movement.created_at ||
                  movement.data;
                return (
                  <Link
                    key={movement.id || `${title}-${index}`}
                    to={movement.case_id ? `/casos/${movement.case_id}` : "/casos"}
                    className="ejc-premium-feed__item"
                  >
                    <span className="ejc-premium-feed__icon">
                      <Gavel aria-hidden="true" />
                    </span>
                    <span className="ejc-premium-feed__copy">
                      <strong>{title}</strong>
                      <small>
                        {[process, movement.cliente_nome]
                          .filter(Boolean)
                          .join(" · ") || "Processo relacionado"}
                      </small>
                    </span>
                    <span className="ejc-premium-feed__meta">
                      <time>{formatDateTime(when)}</time>
                      {movement.status && (
                        <StatusBadge value={movement.status} />
                      )}
                    </span>
                  </Link>
                );
              })}
            </div>
          )}
        </Panel>

        <Panel
          title="Agenda da Semana"
          action={
            <Link
              to="/atividades?view=calendario"
              className="ejc-premium-panel__link"
            >
              Ver agenda
            </Link>
          }
        >
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3, 4].map((item) => (
                <div key={item} className="ejc-skeleton h-16 w-full" />
              ))}
            </div>
          ) : agendaUnavailable ? (
            <EmptyState
              title="Agenda indisponível"
              message="A central de atividades não respondeu. Nenhum compromisso fictício foi criado."
              icon={CalendarClock}
            />
          ) : weeklyAgenda.length === 0 ? (
            <EmptyState
              title="Semana sem compromissos"
              message="Nenhuma atividade foi localizada na semana atual."
              icon={CalendarClock}
            />
          ) : (
            <div className="ejc-premium-agenda">
              {weeklyAgenda.map((item, index) => {
                const day = item.date
                  ? new Date(
                      item.date.includes("T")
                        ? item.date
                        : `${item.date}T12:00:00`,
                    )
                  : null;
                return (
                  <Link
                    key={item.id || `${item.titulo}-${index}`}
                    to={item.case_id ? `/casos/${item.case_id}` : "/atividades"}
                    className="ejc-premium-agenda__item"
                  >
                    <span className="ejc-premium-agenda__date">
                      <strong>{day ? String(day.getDate()).padStart(2, "0") : "--"}</strong>
                      <small>
                        {day
                          ? day
                              .toLocaleDateString("pt-BR", { month: "short" })
                              .replace(".", "")
                          : "data"}
                      </small>
                    </span>
                    <span className="ejc-premium-agenda__copy">
                      <strong>{item.titulo || "Compromisso"}</strong>
                      <small>
                        {[item.hora, item.local, item.caso_titulo]
                          .filter(Boolean)
                          .join(" · ") || "Detalhes na central de atividades"}
                      </small>
                    </span>
                    {item.status && <StatusBadge value={item.status} />}
                  </Link>
                );
              })}
            </div>
          )}
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr_0.95fr]">
        <Panel
          title="Distribuição por Área"
          action={
            <Link to="/areas-de-atuacao" className="ejc-premium-panel__link">
              Ver relatório
            </Link>
          }
        >
          {loading ? (
            <div className="space-y-4">
              {[1, 2, 3, 4].map((item) => (
                <div key={item} className="ejc-skeleton h-9 w-full" />
              ))}
            </div>
          ) : casesUnavailable ? (
            <EmptyState
              title="Distribuição indisponível"
              message="O bloco de casos por área não pôde ser calculado."
              icon={BriefcaseBusiness}
            />
          ) : areas.length === 0 ? (
            <EmptyState
              title="Sem áreas contabilizadas"
              message="Não há processos classificados por área de atuação."
              icon={BriefcaseBusiness}
            />
          ) : (
            <div className="ejc-premium-areas">
              {areas.map((area, index) => (
                <div key={area.label}>
                  <span>
                    <BriefcaseBusiness aria-hidden="true" />
                    <strong>{area.label}</strong>
                  </span>
                  <i>
                    <b
                      style={{
                        width: `${Math.max(5, (area.value / maxArea) * 100)}%`,
                        background:
                          index % 2 === 0 ? "#c9a227" : "#101923",
                      }}
                    />
                  </i>
                  <em>{area.value}</em>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel
          title="Processos por Status"
          action={
            <Link to="/casos" className="ejc-premium-panel__link">
              Ver todos
            </Link>
          }
        >
          {loading ? (
            <div className="ejc-skeleton h-64 w-full" />
          ) : casesUnavailable ? (
            <EmptyState
              title="Status indisponíveis"
              message="O bloco de processos por status não pôde ser calculado."
              icon={CircleGauge}
            />
          ) : statusEntries.length === 0 ? (
            <EmptyState
              title="Sem processos contabilizados"
              message="Nenhum status processual foi retornado."
              icon={CircleGauge}
            />
          ) : (
            <div className="ejc-premium-status">
              <div
                className="ejc-premium-status__donut"
                style={{ background: donutGradient }}
                role="img"
                aria-label={`Distribuição de ${totalCases} processos por status`}
              >
                <span>
                  <strong>{totalCases}</strong>
                  <small>Total</small>
                </span>
              </div>
              <div className="ejc-premium-status__legend">
                {statusEntries.slice(0, 6).map((entry) => (
                  <div key={entry.label}>
                    <i style={{ background: entry.color }} />
                    <span>{entry.label}</span>
                    <strong>{entry.value}</strong>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Panel>

        <Panel title="Atalhos Rápidos">
          <div className="ejc-premium-actions">
            {quickActions.map(({ to, label, icon: Icon }) => (
              <Link key={`${to}-${label}`} to={to}>
                <Icon aria-hidden="true" />
                <span>{label}</span>
                <ArrowRight aria-hidden="true" />
              </Link>
            ))}
          </div>
        </Panel>
      </div>

      <div className="ejc-dashboard-premium__integrity">
        <Clock3 aria-hidden="true" />
        <span>
          Indicadores financeiros permanecem exclusivamente no módulo
          Financeiro e não são renderizados neste dashboard compartilhado.
        </span>
      </div>
    </div>
  );
}
