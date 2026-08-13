import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  ArrowRight,
  BrainCircuit,
  CalendarClock,
  CheckCircle2,
  CircleAlert,
  Clock3,
  FilePlus2,
  FolderKanban,
  Gavel,
  Import,
  ListTodo,
  Plus,
  Radar,
  Scale,
  Sparkles,
  UserPlus,
  Users,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router";
import api from "../lib/api";
import { asList } from "../lib/list";
import {
  NOVO_CASO_DOCUMENTO_PATH,
  NOVO_CASO_MANUAL_PATH,
} from "../lib/novoCaso";
import { useAuth } from "../stores/auth";
import { Badge, cn } from "../components/UI";

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
  "#182534",
  "#a67c34",
  "#7a8794",
  "#d8dee5",
  "#e5ce7f",
];

function formatArea(value?: string) {
  if (!value) return "Outros";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDateTime(value?: string) {
  if (!value) return "Data não informada";
  const parsed = new Date(value.includes("T") ? value : `${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return "Data não informada";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: value.includes("T") ? "2-digit" : undefined,
    minute: value.includes("T") ? "2-digit" : undefined,
  }).format(parsed);
}

function dateKey(value?: string) {
  return value?.slice(0, 10) ?? "";
}

function isFinalActivity(status?: string) {
  return FINAL_ACTIVITY_STATUSES.has((status || "").toLowerCase());
}

function agendaTimestamp(item: Pick<ActivityItem, "date" | "hora">) {
  if (!item.date) return Number.POSITIVE_INFINITY;
  const data = item.date.slice(0, 10);
  const hora = /^\d{2}:\d{2}/.test(item.hora || "")
    ? String(item.hora).slice(0, 5)
    : "12:00";
  const parsed = new Date(`${data}T${hora}:00`);
  return Number.isNaN(parsed.getTime())
    ? Number.POSITIVE_INFINITY
    : parsed.getTime();
}

function buildDonutGradient(entries: Array<{ value: number; color: string }>) {
  const total = entries.reduce((sum, entry) => sum + entry.value, 0);
  if (total <= 0) return "conic-gradient(#e5e7eb 0 100%)";
  let cursor = 0;
  return `conic-gradient(${entries
    .map((entry, index) => {
      const start = cursor;
      cursor += (entry.value / total) * 100;
      const end = index === entries.length - 1 ? 100 : cursor;
      return `${entry.color} ${start.toFixed(2)}% ${end.toFixed(2)}%`;
    })
    .join(", ")})`;
}

function Surface({
  title,
  eyebrow,
  action,
  children,
  className,
}: {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("ejc-ultra-surface", className)}>
      <header className="ejc-ultra-surface__header">
        <div>
          {eyebrow && <span className="be-bronze-accent">{eyebrow}</span>}
          <h2 className="be-section-title">{title}</h2>
        </div>
        {action}
      </header>
      <div className="ejc-ultra-surface__body">{children}</div>
    </section>
  );
}

function Metric({
  label,
  value,
  helper,
  icon: Icon,
  to,
  loading,
  unavailable,
  tone = "default",
}: {
  label: string;
  value: number | null;
  helper: string;
  icon: LucideIcon;
  to: string;
  loading: boolean;
  unavailable: boolean;
  tone?: "default" | "attention" | "success" | "tech";
}) {
  return (
    <Link
      to={to}
      className={cn(
        "ejc-ultra-metric",
        `is-${tone}`,
        unavailable && "is-muted",
      )}
    >
      <span className="ejc-ultra-metric__icon">
        <Icon aria-hidden="true" />
      </span>
      <span className="ejc-ultra-metric__copy">
        <small>{label}</small>
        {loading ? (
          <i
            className="ejc-ultra-skeleton"
            role="status"
            aria-label="Carregando"
          />
        ) : (
          <strong>{unavailable ? "—" : (value ?? 0)}</strong>
        )}
        <em>{unavailable ? "Fonte indisponível" : helper}</em>
      </span>
      <ArrowRight className="ejc-ultra-metric__arrow" aria-hidden="true" />
    </Link>
  );
}

export default function DashboardUltra() {
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
      api.get("/movimentos/recentes", { params: { limit: 8 } }),
    ])
      .then(
        ([dashboardResult, activitiesResult, agendaResult, movementResult]) => {
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
        },
      )
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

  const upcomingAgenda = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
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
        if (!item.date || isFinalActivity(item.status)) return false;
        const parsed = new Date(
          item.date.includes("T") ? item.date : `${item.date}T12:00:00`,
        );
        return parsed >= today;
      })
      .sort((a, b) => agendaTimestamp(a) - agendaTimestamp(b))
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
  const maxArea = Math.max(1, ...areas.map((item) => item.value));
  const totalCases = Number(dashboard?.casos?.total || 0);
  const firstName = user?.full_name?.split(" ")[0] || "colega";
  const canCreateCase = CREATE_CASE_ROLES.has(user?.role || "");
  const canUseLegal = LEGAL_ROLES.has(user?.role || "");

  const quickActions = [
    ...(canCreateCase
      ? [
          {
            to: NOVO_CASO_DOCUMENTO_PATH,
            label: "Novo caso por documento",
            detail: "IA extrai e estrutura os dados",
            icon: FilePlus2,
          },
          {
            to: NOVO_CASO_MANUAL_PATH,
            label: "Novo caso manual",
            detail: "Cadastro direto e controlado",
            icon: Plus,
          },
          {
            to: "/clientes",
            label: "Clientes",
            detail: "Cadastro e histórico de atendimento",
            icon: UserPlus,
          },
        ]
      : []),
    {
      to: "/atividades?view=calendario",
      label: "Agenda e prazos",
      detail: "Central operacional do dia",
      icon: CalendarClock,
    },
    ...(canUseLegal
      ? [
          {
            to: "/entrada",
            label: "Importar documento",
            detail: "Entrada única de documentos",
            icon: Import,
          },
          {
            to: "/inteligencia",
            label: "Inteligência jurídica",
            detail: "Análise, estratégia e pesquisa",
            icon: BrainCircuit,
          },
        ]
      : []),
  ].slice(0, 6);

  const riskCount =
    Number(dashboard?.prazos?.vencidos || 0) +
    Number(dashboard?.prazos?.criticos_3d || 0);

  return (
    <div className="ejc-ultra-dashboard">
      <section className="ejc-ultra-hero">
        <div className="ejc-ultra-hero__grid" aria-hidden="true" />
        <div className="ejc-ultra-hero__content">
          <div className={cn("ejc-ultra-hero__eyebrow", "be-hero-eyebrow")}>
            <Radar aria-hidden="true" />
            <span>Legal Operations Command Center</span>
            <i>SNAPSHOT</i>
          </div>
          <h1 className="be-hero-title">Bom trabalho, {firstName}.</h1>
          <p>
            Uma visão única de casos, prazos, tarefas e movimentações para
            decidir o que exige atenção agora. Dados carregados ao abrir a tela.
          </p>
          <div className="ejc-ultra-hero__actions">
            {canCreateCase && (
              <Link
                to={NOVO_CASO_DOCUMENTO_PATH}
                className="ejc-ultra-primary-action"
              >
                <Sparkles aria-hidden="true" />
                Abrir caso com documento
              </Link>
            )}
            <Link to="/casos" className="ejc-ultra-secondary-action">
              <FolderKanban aria-hidden="true" />
              Ver carteira
            </Link>
          </div>
        </div>
        <div
          className="ejc-ultra-hero__signal"
          aria-label="Resumo de atenção operacional"
        >
          <div className="ejc-ultra-orbit" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <div className="ejc-ultra-hero__signal-copy">
            <small>Índice de atenção</small>
            <strong>{deadlinesUnavailable ? "—" : riskCount}</strong>
            <span>
              {deadlinesUnavailable
                ? "Prazos indisponíveis"
                : riskCount > 0
                  ? "itens de prazo requerem revisão"
                  : "operação sem prazo crítico detectado"}
            </span>
          </div>
        </div>
      </section>

      <section
        className="ejc-ultra-metrics"
        aria-label="Indicadores operacionais"
      >
        <Metric
          label="Casos ativos"
          value={dashboard?.casos?.ativos ?? null}
          helper="carteira em andamento"
          icon={Scale}
          to="/casos?status=ativo"
          loading={loading}
          unavailable={casesUnavailable}
          tone="tech"
        />
        <Metric
          label="Prazos em 7 dias"
          value={dashboard?.prazos?.proximos_7d ?? null}
          helper="janela operacional imediata"
          icon={CalendarClock}
          to="/atividades?tipo=prazo"
          loading={loading}
          unavailable={deadlinesUnavailable}
          tone={riskCount > 0 ? "attention" : "default"}
        />
        <Metric
          label="Tarefas pendentes"
          value={pendingTasks}
          helper="ações ainda não concluídas"
          icon={ListTodo}
          to="/atividades?tipo=tarefa"
          loading={loading}
          unavailable={tasksUnavailable}
        />
        <Metric
          label="Total da carteira"
          value={dashboard?.casos?.total ?? null}
          helper="casos registrados no EJC"
          icon={Gavel}
          to="/casos"
          loading={loading}
          unavailable={casesUnavailable}
          tone="success"
        />
      </section>

      <div className="ejc-ultra-main-grid">
        <Surface
          eyebrow="Prioridade"
          title="Radar operacional"
          className="ejc-ultra-radar-panel"
          action={
            <Link to="/atividades" className="ejc-ultra-text-link">
              Abrir central <ArrowRight aria-hidden="true" />
            </Link>
          }
        >
          <div className="ejc-ultra-priority-list">
            <Link
              to="/atividades?tipo=prazo"
              className="ejc-ultra-priority is-critical"
            >
              <span className="ejc-ultra-priority__icon">
                <CircleAlert aria-hidden="true" />
              </span>
              <span>
                <small>Prazos vencidos</small>
                <strong>
                  {deadlinesUnavailable
                    ? "—"
                    : (dashboard?.prazos?.vencidos ?? 0)}
                </strong>
              </span>
              <em>tratar primeiro</em>
            </Link>
            <Link
              to="/atividades?tipo=prazo"
              className="ejc-ultra-priority is-warning"
            >
              <span className="ejc-ultra-priority__icon">
                <Clock3 aria-hidden="true" />
              </span>
              <span>
                <small>Críticos em 3 dias</small>
                <strong>
                  {deadlinesUnavailable
                    ? "—"
                    : (dashboard?.prazos?.criticos_3d ?? 0)}
                </strong>
              </span>
              <em>janela curta</em>
            </Link>
            <Link
              to="/atividades?tipo=tarefa"
              className="ejc-ultra-priority is-neutral"
            >
              <span className="ejc-ultra-priority__icon">
                <CheckCircle2 aria-hidden="true" />
              </span>
              <span>
                <small>Tarefas pendentes</small>
                <strong>{tasksUnavailable ? "—" : pendingTasks}</strong>
              </span>
              <em>organizar execução</em>
            </Link>
          </div>

          <div className="ejc-ultra-agenda-head">
            <div>
              <span>Próximos compromissos</span>
              <small>agenda real do EJC</small>
            </div>
          </div>
          {loading ? (
            <div className="ejc-ultra-list-loading">Carregando agenda…</div>
          ) : failed.activities ? (
            <div className="ejc-ultra-empty">
              Agenda indisponível no momento.
            </div>
          ) : upcomingAgenda.length === 0 ? (
            <div className="ejc-ultra-empty">
              Nenhuma atividade futura encontrada.
            </div>
          ) : (
            <div className="ejc-ultra-agenda-list">
              {failed.agenda && (
                <div className="ejc-ultra-empty" role="status">
                  Horário, local e subtipo dos compromissos podem estar
                  indisponíveis no momento.
                </div>
              )}
              {upcomingAgenda.map((item, index) => {
                const destination = item.case_id
                  ? `/casos/${item.case_id}`
                  : "/atividades";
                return (
                  <Link
                    key={item.id || `${dateKey(item.date)}-${index}`}
                    to={destination}
                    className="ejc-ultra-agenda-item"
                  >
                    <span className="ejc-ultra-agenda-item__date">
                      {formatDateTime(item.date)}
                    </span>
                    <span className="ejc-ultra-agenda-item__copy">
                      <strong>
                        {item.titulo || item.caso_titulo || "Atividade"}
                      </strong>
                      <small>
                        {[
                          item.hora,
                          item.local,
                          formatArea(item.subtipo || item.tipo),
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </small>
                    </span>
                    <ArrowRight aria-hidden="true" />
                  </Link>
                );
              })}
            </div>
          )}
        </Surface>

        <Surface eyebrow="Carteira" title="Distribuição dos casos">
          {loading ? (
            <div className="ejc-ultra-portfolio-loading">
              Carregando carteira…
            </div>
          ) : casesUnavailable ? (
            <div className="ejc-ultra-empty">Dados de casos indisponíveis.</div>
          ) : totalCases === 0 ? (
            <div className="ejc-ultra-empty">Nenhum caso registrado.</div>
          ) : (
            <div className="ejc-ultra-portfolio">
              <div className="ejc-ultra-donut-wrap">
                <div
                  className="ejc-ultra-donut"
                  style={{ background: donutGradient }}
                  aria-label={`${totalCases} casos no total`}
                >
                  <div>
                    <small>Total</small>
                    <strong>{totalCases}</strong>
                    <span>casos</span>
                  </div>
                </div>
                <div className="ejc-ultra-status-legend">
                  {statusEntries.slice(0, 5).map((item) => (
                    <div key={item.label}>
                      <i style={{ backgroundColor: item.color }} />
                      <span>{item.label}</span>
                      <strong>{item.value}</strong>
                    </div>
                  ))}
                </div>
              </div>

              <div className="ejc-ultra-area-bars">
                <div className="ejc-ultra-area-bars__title">
                  <span>Áreas de atuação</span>
                  <Badge tone="ouro">Top {areas.length}</Badge>
                </div>
                {areas.length === 0 ? (
                  <div className="ejc-ultra-empty">
                    Sem distribuição por área.
                  </div>
                ) : (
                  areas.map((item) => (
                    <div className="ejc-ultra-area-row" key={item.label}>
                      <div>
                        <span>{item.label}</span>
                        <strong>{item.value}</strong>
                      </div>
                      <div className="ejc-ultra-area-track">
                        <i
                          style={{
                            width: `${Math.max(6, (item.value / maxArea) * 100)}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </Surface>
      </div>

      <div className="ejc-ultra-bottom-grid">
        <Surface
          eyebrow="Timeline"
          title="Movimentações recentes"
          action={
            <Link to="/casos" className="ejc-ultra-text-link">
              Ver casos <ArrowRight aria-hidden="true" />
            </Link>
          }
        >
          {loading ? (
            <div className="ejc-ultra-list-loading">
              Carregando movimentações…
            </div>
          ) : failed.movements ? (
            <div className="ejc-ultra-empty">Movimentações indisponíveis.</div>
          ) : movements.length === 0 ? (
            <div className="ejc-ultra-empty">Nenhuma movimentação recente.</div>
          ) : (
            <div className="ejc-ultra-timeline">
              {movements.slice(0, 6).map((movement, index) => {
                const date =
                  movement.data_movimento ||
                  movement.created_at ||
                  movement.data;
                const destination = movement.case_id
                  ? `/casos/${movement.case_id}`
                  : "/casos";
                return (
                  <Link
                    key={movement.id || `${date}-${index}`}
                    to={destination}
                    className="ejc-ultra-timeline__item"
                  >
                    <span className="ejc-ultra-timeline__node">
                      <Activity aria-hidden="true" />
                    </span>
                    <span className="ejc-ultra-timeline__copy">
                      <small>{formatDateTime(date)}</small>
                      <strong>
                        {movement.descricao ||
                          movement.titulo ||
                          formatArea(movement.tipo) ||
                          "Movimentação"}
                      </strong>
                      <em>
                        {movement.case_title ||
                          movement.cliente_nome ||
                          movement.case_number ||
                          movement.numero_processo ||
                          "Caso relacionado"}
                      </em>
                    </span>
                  </Link>
                );
              })}
            </div>
          )}
        </Surface>

        <Surface
          eyebrow="Comandos"
          title="Acesso rápido"
          className="ejc-ultra-command-panel"
        >
          <div className="ejc-ultra-command-grid">
            {quickActions.map(({ to, label, detail, icon: Icon }) => (
              <Link
                to={to}
                key={`${to}-${label}`}
                className="ejc-ultra-command"
              >
                <span>
                  <Icon aria-hidden="true" />
                </span>
                <strong>{label}</strong>
                <small>{detail}</small>
                <ArrowRight aria-hidden="true" />
              </Link>
            ))}
          </div>
          <div className="ejc-ultra-command-foot">
            <Zap aria-hidden="true" />
            <span>
              Interface orientada a decisão: atalhos levam aos módulos
              existentes e respeitam RBAC.
            </span>
          </div>
        </Surface>
      </div>

      <div className="ejc-ultra-privacy-note">
        <Users aria-hidden="true" />
        <span>
          Dashboard operacional compartilhado — sem informações financeiras.
        </span>
      </div>
    </div>
  );
}
