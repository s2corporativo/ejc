import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  CalendarDays,
  CheckCircle2,
  CircleDot,
  ClipboardCheck,
  FileCheck2,
  FileText,
  Gavel,
  ListTodo,
  Scale,
  Send,
  ShieldCheck,
  Sparkles,
  Users,
  type LucideIcon,
} from "lucide-react";
import { Link, useNavigate } from "react-router";
import api from "../lib/api";
import { asList } from "../lib/list";
import { useAuth } from "../stores/auth";

interface DashboardPayload {
  casos?: {
    por_status?: Record<string, number>;
    total?: number;
    ativos?: number;
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

interface ClientItem {
  id: string;
  nome?: string;
  status?: string;
  email?: string;
  telefone?: string;
  whatsapp?: string;
}

interface DefesasMeta {
  modalidades?: Array<{
    codigo?: string;
    titulo?: string;
    descricao?: string;
  }>;
}

const FINAL_ACTIVITY_STATUSES = new Set([
  "concluido",
  "concluida",
  "tratada",
  "cancelado",
  "cancelada",
  "arquivado",
  "arquivada",
  "encerrado",
  "encerrada",
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
  "#17985a",
  "#62c489",
  "#e89a1b",
  "#df3f49",
  "#8090a5",
  "#2f7dd1",
];

function formatLabel(value?: string) {
  if (!value) return "Outros";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function localDateKey(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseDate(value?: string, time?: string) {
  if (!value) return null;
  const day = value.slice(0, 10);
  const hour = /^\d{2}:\d{2}/.test(time || "")
    ? String(time).slice(0, 5)
    : "12:00";
  const parsed = new Date(`${day}T${hour}:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function activityTimestamp(item: Pick<ActivityItem, "date" | "hora">) {
  return parseDate(item.date, item.hora)?.getTime() ?? Number.POSITIVE_INFINITY;
}

function formatDayMeta(item: Pick<ActivityItem, "date" | "hora">) {
  const parsed = parseDate(item.date, item.hora);
  if (!parsed)
    return { day: "—", month: "", relative: "", time: item.hora || "" };

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(parsed);
  target.setHours(0, 0, 0, 0);
  const diff = Math.round((target.getTime() - today.getTime()) / 86_400_000);
  const relative = diff === 0 ? "Hoje" : diff === 1 ? "Amanhã" : "";

  return {
    day: String(parsed.getDate()).padStart(2, "0"),
    month: new Intl.DateTimeFormat("pt-BR", { month: "short" })
      .format(parsed)
      .replace(".", "")
      .toUpperCase(),
    relative,
    time: item.hora?.slice(0, 5) || "",
  };
}

function isFinalActivity(status?: string) {
  return FINAL_ACTIVITY_STATUSES.has((status || "").toLowerCase());
}

function isTask(item: ActivityItem) {
  return item.tipo === "tarefa" || item.fonte === "tarefa";
}

function isIntimation(item: ActivityItem) {
  const kind =
    `${item.tipo || ""} ${item.subtipo || ""} ${item.fonte || ""}`.toLowerCase();
  return kind.includes("intimacao") || kind.includes("intimação");
}

function buildDonutGradient(entries: Array<{ value: number; color: string }>) {
  const total = entries.reduce((sum, entry) => sum + entry.value, 0);
  if (total <= 0) return "conic-gradient(#e6ebf1 0 100%)";
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

function Card({
  title,
  icon: Icon,
  action,
  children,
  className = "",
}: {
  title: string;
  icon: LucideIcon;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`ejc-reference-card ${className}`}>
      <header className="ejc-reference-card__header">
        <div className="ejc-reference-card__title">
          <Icon aria-hidden="true" />
          <span>{title}</span>
        </div>
        {action}
      </header>
      <div className="ejc-reference-divider" />
      <div className="ejc-reference-card__body">{children}</div>
    </section>
  );
}

function MoreLink({
  to,
  children = "Ver todos",
}: {
  to: string;
  children?: ReactNode;
}) {
  return (
    <Link to={to} className="ejc-reference-card__action">
      {children} <ArrowRight aria-hidden="true" />
    </Link>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <div className="ejc-reference-empty">{children}</div>;
}

export default function DashboardUltra() {
  const navigate = useNavigate();
  const user = useAuth((state) => state.user);
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [agendaEvents, setAgendaEvents] = useState<AgendaEvent[]>([]);
  const [clients, setClients] = useState<ClientItem[]>([]);
  const [defesasMeta, setDefesasMeta] = useState<DefesasMeta | null>(null);
  const [taskTab, setTaskTab] = useState<"tarefas" | "intimacoes">("tarefas");
  const [quickQuestion, setQuickQuestion] = useState("");
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState({
    dashboard: false,
    activities: false,
    agenda: false,
    clients: false,
  });

  useEffect(() => {
    let active = true;
    setLoading(true);

    Promise.allSettled([
      api.get("/dashboard/"),
      api.get("/atividades", { params: { apenas_pendentes: false } }),
      api.get("/agenda-eventos/", { params: { page_size: 500 } }),
      api.get("/clients/?page_size=4&status=ativo"),
      api.get("/defesas-revisoes/meta"),
    ])
      .then(
        ([
          dashboardResult,
          activitiesResult,
          agendaResult,
          clientsResult,
          defesasResult,
        ]) => {
          if (!active) return;

          setFailed({
            dashboard: dashboardResult.status === "rejected",
            activities: activitiesResult.status === "rejected",
            agenda: agendaResult.status === "rejected",
            clients: clientsResult.status === "rejected",
          });

          if (dashboardResult.status === "fulfilled")
            setDashboard(dashboardResult.value.data);
          if (activitiesResult.status === "fulfilled")
            setActivities(asList(activitiesResult.value.data));
          if (agendaResult.status === "fulfilled")
            setAgendaEvents(asList(agendaResult.value.data));
          if (clientsResult.status === "fulfilled")
            setClients(asList<ClientItem>(clientsResult.value.data));
          if (defesasResult.status === "fulfilled")
            setDefesasMeta(defesasResult.value.data);
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
  const deadlinesUnavailable = failed.dashboard || degraded.has("prazos");
  const casesUnavailable = failed.dashboard || degraded.has("casos");

  const pendingTasks = useMemo(
    () =>
      activities.filter(
        (item) => isTask(item) && !isFinalActivity(item.status),
      ),
    [activities],
  );

  const pendingIntimations = useMemo(
    () =>
      activities.filter(
        (item) => isIntimation(item) && !isFinalActivity(item.status),
      ),
    [activities],
  );

  const todayTasks = useMemo(() => {
    const today = localDateKey();
    return pendingTasks.filter((item) => item.date?.slice(0, 10) === today)
      .length;
  }, [pendingTasks]);

  const agendaMap = useMemo(() => {
    const map = new Map<string, AgendaEvent>();
    for (const event of agendaEvents) if (event.id) map.set(event.id, event);
    return map;
  }, [agendaEvents]);

  const upcomingAgenda = useMemo(() => {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
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
        const parsed = parseDate(item.date, item.hora);
        return parsed && parsed >= start && !isFinalActivity(item.status);
      })
      .sort((a, b) => activityTimestamp(a) - activityTimestamp(b))
      .slice(0, 3);
  }, [activities, agendaMap]);

  const statusEntries = useMemo(
    () =>
      Object.entries(dashboard?.casos?.por_status || {})
        .map(([label, value], index) => ({
          label: formatLabel(label),
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
  const taskItems = taskTab === "tarefas" ? pendingTasks : pendingIntimations;
  const canUseLegal = LEGAL_ROLES.has(user?.role || "");
  const contractFeature = defesasMeta?.modalidades?.find(
    (item) => item.codigo === "revisao_contratual",
  );
  const trafficFeature = defesasMeta?.modalidades?.find(
    (item) => item.codigo === "multa_transito",
  );

  const submitQuickQuestion = () => {
    const q = quickQuestion.trim();
    if (!q) return;
    navigate("/inteligencia?tab=assistente&sub=rapido", {
      state: { perguntaRapida: q },
    });
  };

  return (
    <div className="ejc-reference-dashboard">
      <div className="ejc-reference-dashboard__top">
        <Card
          title="Prioridades"
          icon={ClipboardCheck}
          action={<MoreLink to="/atividades">Ver todas</MoreLink>}
        >
          <Link
            to="/atividades?tipo=prazo"
            className="ejc-reference-row ejc-reference-accent-row is-danger"
          >
            <span className="ejc-reference-row__icon is-danger">
              <Scale aria-hidden="true" />
            </span>
            <span className="ejc-reference-row__copy">
              <strong>
                {deadlinesUnavailable
                  ? "—"
                  : (dashboard?.prazos?.vencidos ?? 0)}{" "}
                prazos vencidos
              </strong>
              <small>Exigem conferência e atuação imediata</small>
            </span>
            <ArrowRight size={12} aria-hidden="true" />
          </Link>
          <Link
            to="/atividades?tipo=prazo"
            className="ejc-reference-row ejc-reference-accent-row is-warning"
          >
            <span className="ejc-reference-row__icon is-warning">
              <AlertTriangle aria-hidden="true" />
            </span>
            <span className="ejc-reference-row__copy">
              <strong>
                {deadlinesUnavailable
                  ? "—"
                  : (dashboard?.prazos?.criticos_3d ?? 0)}{" "}
                prazos críticos em 3 dias
              </strong>
              <small>Janela operacional curta</small>
            </span>
            <ArrowRight size={12} aria-hidden="true" />
          </Link>
          <Link
            to="/atividades?tipo=tarefa"
            className="ejc-reference-row ejc-reference-accent-row"
          >
            <span className="ejc-reference-row__icon">
              <CalendarDays aria-hidden="true" />
            </span>
            <span className="ejc-reference-row__copy">
              <strong>
                {failed.activities ? "—" : todayTasks} tarefas para hoje
              </strong>
              <small>Atividades pendentes com data de hoje</small>
            </span>
            <ArrowRight size={12} aria-hidden="true" />
          </Link>
          <Link
            to="/atividades?tipo=intimacao"
            className="ejc-reference-row ejc-reference-accent-row is-success"
          >
            <span className="ejc-reference-row__icon is-success">
              <Bell aria-hidden="true" />
            </span>
            <span className="ejc-reference-row__copy">
              <strong>
                {failed.activities ? "—" : pendingIntimations.length} intimações
                pendentes
              </strong>
              <small>Comunicações processuais a tratar</small>
            </span>
            <ArrowRight size={12} aria-hidden="true" />
          </Link>
        </Card>

        <Card
          title="Tarefas e Intimações"
          icon={ListTodo}
          action={<MoreLink to="/atividades">Ver todas</MoreLink>}
        >
          <div
            className="ejc-reference-tabs"
            role="tablist"
            aria-label="Tarefas e intimações"
          >
            <button
              type="button"
              role="tab"
              aria-selected={taskTab === "tarefas"}
              className={taskTab === "tarefas" ? "is-active" : undefined}
              onClick={() => setTaskTab("tarefas")}
            >
              Tarefas
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={taskTab === "intimacoes"}
              className={taskTab === "intimacoes" ? "is-active" : undefined}
              onClick={() => setTaskTab("intimacoes")}
            >
              Intimações
            </button>
          </div>
          {loading ? (
            <Empty>Carregando atividades…</Empty>
          ) : failed.activities ? (
            <Empty>Atividades temporariamente indisponíveis.</Empty>
          ) : taskItems.length === 0 ? (
            <Empty>Nenhum item pendente nesta aba.</Empty>
          ) : (
            taskItems.slice(0, 4).map((item, index) => {
              const meta = formatDayMeta(item);
              return (
                <Link
                  key={item.id || `${item.titulo}-${index}`}
                  to={
                    item.case_id
                      ? `/casos/${item.case_id}`
                      : taskTab === "tarefas"
                        ? "/atividades?tipo=tarefa"
                        : "/atividades?tipo=intimacao"
                  }
                  className="ejc-reference-row"
                >
                  <span className="ejc-reference-task-dot" aria-hidden="true" />
                  <span className="ejc-reference-row__copy">
                    <strong>
                      {item.titulo ||
                        (taskTab === "tarefas" ? "Tarefa" : "Intimação")}
                    </strong>
                    <small>
                      {item.caso_titulo ||
                        item.descricao ||
                        formatLabel(item.subtipo || item.tipo)}
                    </small>
                  </span>
                  <span className="ejc-reference-row__meta">
                    {meta.relative && <strong>{meta.relative}</strong>}
                    <span>{meta.time || `${meta.day} ${meta.month}`}</span>
                  </span>
                </Link>
              );
            })
          )}
        </Card>

        <Card
          title="Inteligência Jurídica"
          icon={Sparkles}
          action={
            canUseLegal ? (
              <MoreLink to="/inteligencia">Abrir completa</MoreLink>
            ) : undefined
          }
        >
          {canUseLegal ? (
            <>
              <p className="ejc-reference-ai-copy">
                Pergunte algo rápido ou abra uma ferramenta jurídica
                especializada.
              </p>
              <div className="ejc-reference-ai-box">
                <textarea
                  value={quickQuestion}
                  onChange={(event) => setQuickQuestion(event.target.value)}
                  onKeyDown={(event) => {
                    if (
                      (event.ctrlKey || event.metaKey) &&
                      event.key === "Enter"
                    )
                      submitQuickQuestion();
                  }}
                  placeholder="Digite sua pergunta ou descreva o que precisa (ex.: jurisprudência sobre dano moral em acidente de trânsito)…"
                  aria-label="Pergunta rápida para a Inteligência Jurídica"
                />
                <button
                  type="button"
                  className="ejc-reference-ai-send"
                  onClick={submitQuickQuestion}
                  disabled={!quickQuestion.trim()}
                  aria-label="Abrir pergunta na Inteligência Jurídica"
                >
                  <Send aria-hidden="true" />
                </button>
              </div>
              <div className="ejc-reference-ai-shortcuts">
                <Link
                  to="/inteligencia?tab=conhecimento&sub=pesquisa"
                  className="ejc-reference-ai-shortcut"
                >
                  <Scale aria-hidden="true" /> Jurisprudência e fontes
                </Link>
                <Link
                  to="/inteligencia?tab=producao&sub=analise"
                  className="ejc-reference-ai-shortcut"
                >
                  <FileText aria-hidden="true" /> Analisar / produzir peça
                </Link>
                <Link
                  to="/inteligencia?tab=assistente&sub=rapido"
                  className="ejc-reference-ai-shortcut"
                >
                  <ListTodo aria-hidden="true" /> Resumo rápido
                </Link>
                <Link
                  to="/inteligencia?tab=assistente&sub=agente"
                  className="ejc-reference-ai-shortcut"
                >
                  <ShieldCheck aria-hidden="true" /> Análise aprofundada
                </Link>
              </div>
            </>
          ) : (
            <Empty>
              Inteligência Jurídica disponível apenas aos perfis jurídicos
              autorizados.
            </Empty>
          )}
        </Card>
      </div>

      <div className="ejc-reference-dashboard__middle">
        <Card
          title="Radar Operacional"
          icon={Gavel}
          action={<MoreLink to="/casos">Ver carteira</MoreLink>}
        >
          {loading ? (
            <Empty>Carregando radar…</Empty>
          ) : casesUnavailable ? (
            <Empty>Dados da carteira indisponíveis.</Empty>
          ) : statusEntries.length === 0 ? (
            <Empty>Nenhum caso com status para exibir.</Empty>
          ) : (
            <div className="ejc-reference-donut-wrap">
              <div
                className="ejc-reference-donut"
                style={{ background: donutGradient }}
                aria-label={`${dashboard?.casos?.total ?? 0} casos na carteira`}
              />
              <div className="ejc-reference-legend">
                {statusEntries.slice(0, 5).map((item) => (
                  <div key={item.label}>
                    <i style={{ background: item.color }} />
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>

        <Card
          title="Agenda e Prazos"
          icon={CalendarDays}
          action={
            <MoreLink to="/atividades?view=calendario">Ver agenda</MoreLink>
          }
        >
          {loading ? (
            <Empty>Carregando agenda…</Empty>
          ) : failed.activities ? (
            <Empty>Agenda temporariamente indisponível.</Empty>
          ) : upcomingAgenda.length === 0 ? (
            <Empty>Nenhum compromisso futuro encontrado.</Empty>
          ) : (
            upcomingAgenda.map((item, index) => {
              const meta = formatDayMeta(item);
              return (
                <Link
                  key={item.id || `${item.titulo}-${index}`}
                  to={item.case_id ? `/casos/${item.case_id}` : "/atividades"}
                  className="ejc-reference-agenda-row"
                >
                  <span className="ejc-reference-date-tile">
                    <strong>{meta.day}</strong>
                    <small>{meta.month}</small>
                  </span>
                  <span className="ejc-reference-row__copy">
                    <strong>
                      {item.titulo || item.caso_titulo || "Atividade"}
                    </strong>
                    <small>
                      {[
                        item.caso_titulo,
                        item.local,
                        formatLabel(item.subtipo || item.tipo),
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </small>
                  </span>
                  <span className="ejc-reference-row__meta">
                    <span>{meta.time || "—"}</span>
                  </span>
                </Link>
              );
            })
          )}
          {failed.agenda && !failed.activities && (
            <div
              className="ejc-reference-empty"
              style={{ minHeight: 28, padding: 4 }}
            >
              Horário/local podem estar incompletos.
            </div>
          )}
        </Card>

        <Card
          title="Clientes"
          icon={Users}
          action={<MoreLink to="/clientes">Ver todos</MoreLink>}
        >
          {loading ? (
            <Empty>Carregando clientes…</Empty>
          ) : failed.clients ? (
            <Empty>Clientes temporariamente indisponíveis.</Empty>
          ) : clients.length === 0 ? (
            <Empty>Nenhum cliente ativo encontrado.</Empty>
          ) : (
            clients.slice(0, 4).map((client) => (
              <Link
                key={client.id}
                to={`/clientes/${client.id}`}
                className="ejc-reference-client-row"
              >
                <div>
                  <strong>{client.nome || "Cliente sem nome"}</strong>
                  <small>
                    {client.email ||
                      client.telefone ||
                      client.whatsapp ||
                      formatLabel(client.status)}
                  </small>
                </div>
                <span
                  className="ejc-reference-client-status"
                  title={
                    client.status
                      ? `Status: ${formatLabel(client.status)}`
                      : "Cliente"
                  }
                >
                  {client.nome?.trim().charAt(0).toUpperCase() || "C"}
                </span>
              </Link>
            ))
          )}
        </Card>

        <Card
          title="Revisão de Contratos"
          icon={FileCheck2}
          action={
            canUseLegal ? (
              <MoreLink to="/ferramentas?abrir=defesas">Abrir módulo</MoreLink>
            ) : undefined
          }
        >
          {canUseLegal ? (
            <>
              <p className="ejc-reference-feature-intro">
                {contractFeature?.descricao ||
                  "Leitura estruturada de cláusulas, riscos, desequilíbrio, rescisão e recomposição."}
              </p>
              <div className="ejc-reference-feature-list">
                <span>
                  <CheckCircle2 aria-hidden="true" /> Inventário de cláusulas e
                  obrigações
                </span>
                <span>
                  <CheckCircle2 aria-hidden="true" /> Riscos, documentos
                  faltantes e estratégia
                </span>
                <span>
                  <CheckCircle2 aria-hidden="true" /> Saída revisável com
                  validação humana
                </span>
              </div>
              <Link
                to="/ferramentas?abrir=defesas"
                className="ejc-reference-feature-cta"
              >
                Nova revisão <ArrowRight aria-hidden="true" />
              </Link>
            </>
          ) : (
            <Empty>Ferramenta restrita à equipe jurídica autorizada.</Empty>
          )}
        </Card>
      </div>

      <div className="ejc-reference-dashboard__bottom">
        <Card
          title="Recurso de Multa de Trânsito"
          icon={CircleDot}
          action={
            canUseLegal ? (
              <MoreLink to="/ferramentas?abrir=defesas">Abrir módulo</MoreLink>
            ) : undefined
          }
        >
          {canUseLegal ? (
            <>
              <p className="ejc-reference-feature-intro">
                {trafficFeature?.descricao ||
                  "Fluxo assistido para defesa prévia e recursos administrativos de trânsito."}
              </p>
              <div className="ejc-reference-workflow">
                <div className="ejc-reference-workflow__step">
                  <span>
                    <CircleDot aria-hidden="true" />
                  </span>
                  <strong>Dados da multa</strong>
                  <small>Notificação, auto e documentos</small>
                </div>
                <span className="ejc-reference-workflow__arrow">
                  <ArrowRight aria-hidden="true" />
                </span>
                <div className="ejc-reference-workflow__step">
                  <span>
                    <ShieldCheck aria-hidden="true" />
                  </span>
                  <strong>Análise de defesa</strong>
                  <small>Prazo, vícios e fundamentos</small>
                </div>
                <span className="ejc-reference-workflow__arrow">
                  <ArrowRight aria-hidden="true" />
                </span>
                <div className="ejc-reference-workflow__step">
                  <span>
                    <FileText aria-hidden="true" />
                  </span>
                  <strong>Gerar rascunho</strong>
                  <small>Peça com revisão obrigatória</small>
                </div>
                <span className="ejc-reference-workflow__arrow">
                  <ArrowRight aria-hidden="true" />
                </span>
                <div className="ejc-reference-workflow__step">
                  <span>
                    <Send aria-hidden="true" />
                  </span>
                  <strong>Revisão e uso</strong>
                  <small>Conferência jurídica antes do protocolo</small>
                </div>
              </div>
              <Link
                to="/ferramentas?abrir=defesas"
                className="ejc-reference-feature-cta"
              >
                Iniciar novo recurso <ArrowRight aria-hidden="true" />
              </Link>
            </>
          ) : (
            <Empty>Ferramenta restrita à equipe jurídica autorizada.</Empty>
          )}
        </Card>

      </div>

      <footer className="ejc-reference-footer">
        © {new Date().getFullYear()} EJC — Ecossistema Jurídico Clóvis · De
        Paula Teixeira Advogados
      </footer>
    </div>
  );
}
