import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  Clock,
  FileText,
  FileUp,
  FolderOpen,
  Gavel,
  MessageSquare,
  PenLine,
  ScanSearch,
  Users,
  type LucideIcon,
} from "lucide-react";
import NoticiasCard from "../components/NoticiasCard";
import api from "../lib/api";
import { asList } from "../lib/list";
import {
  NOVO_CASO_DOCUMENTO_PATH,
  NOVO_CASO_MANUAL_PATH,
} from "../lib/novoCaso";
import { useAuth } from "../stores/auth";

const CRM_ROLES = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "secretaria",
]);

const INACTIVE_CASE_STATUSES = new Set([
  "arquivado",
  "encerrado",
  "cancelado",
  "inativo",
]);

type ActionCard = {
  to: string;
  title: string;
  description: string;
  icon: LucideIcon;
  tone: "navy" | "gold";
};

type Priority = {
  label: string;
  detail: string;
  value: number | string;
  icon: LucideIcon;
  tone: string;
};

function toNumber(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatDate(value?: string) {
  if (!value) return "Sem data";
  const source = value.includes("T") ? value : `${value}T12:00:00`;
  const date = new Date(source);
  if (Number.isNaN(date.getTime())) return "Sem data";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
  }).format(date);
}

function formatTime(value?: string) {
  if (!value || !value.includes("T")) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Bom dia";
  if (hour < 18) return "Boa tarde";
  return "Boa noite";
}

function dateLabel() {
  return new Intl.DateTimeFormat("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(new Date());
}

function Action({ action }: { action: ActionCard }) {
  const Icon = action.icon;
  const isGold = action.tone === "gold";
  return (
    <Link
      to={action.to}
      className="option-one-action-card group flex items-start gap-4 p-5"
    >
      <span
        className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl text-white shadow-sm ${
          isGold
            ? "bg-gradient-to-br from-amber-500 to-amber-700"
            : "bg-gradient-to-br from-primary-800 to-primary-950"
        }`}
      >
        <Icon className="h-6 w-6" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-base font-semibold text-slate-950">
          {action.title}
        </span>
        <span className="mt-1.5 block text-sm leading-6 text-slate-500">
          {action.description}
        </span>
        <span className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-primary-800">
          Abrir
          <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" />
        </span>
      </span>
    </Link>
  );
}

export default function DashboardOptionOne() {
  const user = useAuth((state) => state.user);
  const [dashboard, setDashboard] = useState<any>(null);
  const [deadlines, setDeadlines] = useState<any[]>([]);
  const [movements, setMovements] = useState<any[]>([]);
  const [cases, setCases] = useState<any[]>([]);
  const [serviceSummary, setServiceSummary] = useState<any>(null);
  const [services, setServices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const currentUser = user as any;
  const firstName = currentUser?.full_name?.split(" ")[0] || "Doutor";
  const canSeeCRM = CRM_ROLES.has(currentUser?.role || "");

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      api.get("/dashboard/"),
      api.get("/deadlines/?status=pendente&page_size=100"),
      api.get("/movimentos/recentes?limit=8"),
      api.get("/cases/?page_size=200"),
      canSeeCRM
        ? api.get("/atendimentos/solicitacoes-resumo")
        : Promise.reject(new Error("sem permissão de CRM")),
      canSeeCRM
        ? api.get("/atendimentos?solicitacao_atendida=false&per_page=5")
        : Promise.reject(new Error("sem permissão de CRM")),
    ])
      .then(([dash, deadlineReq, movementReq, caseReq, summaryReq, serviceReq]) => {
        if (dash.status === "fulfilled") setDashboard(dash.value.data);
        if (deadlineReq.status === "fulfilled") {
          setDeadlines(asList(deadlineReq.value.data));
        }
        if (movementReq.status === "fulfilled") {
          setMovements(asList(movementReq.value.data));
        }
        if (caseReq.status === "fulfilled") {
          setCases(asList(caseReq.value.data));
        }
        if (summaryReq.status === "fulfilled") {
          setServiceSummary(summaryReq.value.data);
        }
        if (serviceReq.status === "fulfilled") {
          setServices(asList(serviceReq.value.data));
        }
      })
      .finally(() => setLoading(false));
  }, [canSeeCRM]);

  const orderedDeadlines = useMemo(
    () =>
      [...deadlines]
        .sort((a, b) =>
          String(a.data_prazo || "").localeCompare(String(b.data_prazo || "")),
        )
        .slice(0, 5),
    [deadlines],
  );

  const criticalDeadlines = deadlines.filter(
    (item) => toNumber(item.dias_restantes ?? 99) <= 3,
  );
  const deadlinesToday = deadlines.filter(
    (item) => toNumber(item.dias_restantes ?? 99) === 0,
  ).length;

  const activeCases = cases.filter((item) => {
    const status = String(item.status || "").toLowerCase();
    return !item.archived_at && !INACTIVE_CASE_STATUSES.has(status);
  });

  const attentionCases = activeCases
    .filter((item) => {
      const risk = String(
        item.risco || item.nivel_risco || item.risk_level || "",
      ).toLowerCase();
      return (
        risk.includes("alto") ||
        risk.includes("elevado") ||
        risk.includes("crit") ||
        item.requer_atencao === true
      );
    })
    .slice(0, 5);

  const tasksPending = toNumber(
    dashboard?.tarefas?.pendentes ?? dashboard?.tarefas_pendentes,
  );
  const documentsPending = toNumber(
    dashboard?.documentos?.pendentes_classificacao ??
      dashboard?.documentos_pendentes,
  );
  const piecesPending = toNumber(
    dashboard?.pecas?.aguardando_revisao ?? dashboard?.pecas_revisao,
  );
  const clientsWaiting = toNumber(serviceSummary?.pendentes);
  const highRiskCases = attentionCases.length;

  const actions: ActionCard[] = [
    {
      to: NOVO_CASO_DOCUMENTO_PATH,
      title: "Novo caso com IA",
      description:
        "Envie os documentos, extraia os dados e inicie a jornada com validação humana.",
      icon: FileUp,
      tone: "navy",
    },
    {
      to: NOVO_CASO_MANUAL_PATH,
      title: "Cadastro manual de caso",
      description:
        "Cadastre cliente e caso manualmente em um fluxo objetivo e controlado.",
      icon: PenLine,
      tone: "gold",
    },
    {
      to: "/raio-x",
      title: "Raio-X processual",
      description:
        "Analise documentos sem vincular o processo à carteira do escritório.",
      icon: ScanSearch,
      tone: "navy",
    },
    {
      to: "/clientes",
      title: "Novo atendimento",
      description:
        "Selecione o cliente e registre recado, solicitação, prazo e providência.",
      icon: MessageSquare,
      tone: "gold",
    },
  ];

  const priorities: Priority[] = [
    {
      label: "Prazos críticos",
      detail: `${deadlinesToday} vencendo hoje`,
      value: criticalDeadlines.length,
      icon: CalendarClock,
      tone: "text-red-600 bg-red-50",
    },
    {
      label: "Tarefas pendentes",
      detail: "Ações a acompanhar",
      value: tasksPending,
      icon: CheckCircle2,
      tone: "text-orange-600 bg-orange-50",
    },
    {
      label: "Clientes aguardando",
      detail: "Solicitações sem conclusão",
      value: clientsWaiting,
      icon: Users,
      tone: "text-amber-700 bg-amber-50",
    },
    {
      label: "Documentos pendentes",
      detail: "Aguardando classificação",
      value: documentsPending,
      icon: FileText,
      tone: "text-blue-700 bg-blue-50",
    },
    {
      label: "Peças em revisão",
      detail: "Validação profissional",
      value: piecesPending,
      icon: FolderOpen,
      tone: "text-violet-700 bg-violet-50",
    },
    {
      label: "Casos com risco elevado",
      detail: "Exigem atenção",
      value: highRiskCases,
      icon: AlertTriangle,
      tone: "text-red-700 bg-red-50",
    },
  ];

  return (
    <div className="ejc-option-one-dashboard space-y-5">
      <section className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-950 md:text-3xl">
            {greeting()}, {firstName}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Aqui está o que precisa da sua atenção hoje.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 shadow-sm">
            <span className="font-semibold capitalize text-slate-900">
              {dateLabel()}
            </span>
          </div>
          <Link
            to="/atividades"
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-primary-950 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-primary-900"
          >
            <CalendarClock className="h-4 w-4" />
            Ver agenda do dia
          </Link>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
        {actions.map((action) => (
          <Action key={action.title} action={action} />
        ))}
      </section>

      <section className="option-one-panel overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-slate-950">
              Prioridades de hoje
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              Indicadores operacionais; nenhuma informação financeira é exibida.
            </p>
          </div>
          <Link
            to="/atividades"
            className="text-xs font-semibold text-primary-800 hover:text-primary-950"
          >
            Ver todas as pendências
          </Link>
        </div>
        <div className="grid md:grid-cols-2 xl:grid-cols-6">
          {priorities.map((priority) => {
            const Icon = priority.icon;
            return (
              <div
                key={priority.label}
                className="option-one-priority-item flex min-h-28 items-start gap-3 px-5 py-4"
              >
                <span
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${priority.tone}`}
                >
                  <Icon className="h-4 w-4" />
                </span>
                <span className="min-w-0">
                  <span className="block text-xl font-semibold tabular-nums text-slate-950">
                    {loading ? "—" : priority.value}
                  </span>
                  <span className="mt-0.5 block text-xs font-semibold text-slate-700">
                    {priority.label}
                  </span>
                  <span className="mt-1 block text-[11px] leading-4 text-slate-500">
                    {priority.detail}
                  </span>
                </span>
              </div>
            );
          })}
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-3">
        <div className="option-one-panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
            <div>
              <h2 className="text-base font-semibold">Agenda e prazos</h2>
              <p className="mt-0.5 text-xs text-slate-500">
                Próximos compromissos pendentes
              </p>
            </div>
            <Link
              to="/prazos"
              className="text-xs font-semibold text-primary-800"
            >
              Ver todos
            </Link>
          </div>
          <div className="divide-y divide-slate-100 px-5">
            {loading ? (
              <div className="space-y-3 py-5">
                {[1, 2, 3, 4].map((item) => (
                  <div
                    key={item}
                    className="h-12 animate-pulse rounded-xl bg-slate-100"
                  />
                ))}
              </div>
            ) : orderedDeadlines.length === 0 ? (
              <div className="py-10 text-center text-sm text-slate-400">
                Nenhum prazo pendente.
              </div>
            ) : (
              orderedDeadlines.map((deadline) => {
                const days = toNumber(deadline.dias_restantes ?? 99);
                const critical = days <= 3;
                return (
                  <div key={deadline.id} className="flex gap-3 py-3.5">
                    <div className="w-14 shrink-0 text-xs font-semibold text-slate-500">
                      {formatDate(deadline.data_prazo)}
                    </div>
                    <span
                      className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${
                        critical ? "bg-red-500" : "bg-blue-500"
                      }`}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold text-slate-900">
                        {deadline.titulo || deadline.descricao || "Prazo processual"}
                      </div>
                      <div className="mt-0.5 truncate text-xs text-slate-500">
                        {deadline.numero_processo || deadline.case_title || "Caso vinculado"}
                      </div>
                    </div>
                    <span
                      className={`h-fit rounded-full px-2 py-1 text-[10px] font-semibold ${
                        critical
                          ? "bg-red-50 text-red-700"
                          : "bg-blue-50 text-blue-700"
                      }`}
                    >
                      {days === 0 ? "Hoje" : days < 0 ? "Vencido" : `${days}d`}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="option-one-panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
            <div>
              <h2 className="text-base font-semibold">
                Pendências de atendimento
              </h2>
              <p className="mt-0.5 text-xs text-slate-500">
                Solicitações registradas na linha do tempo
              </p>
            </div>
            <Link
              to="/clientes"
              className="text-xs font-semibold text-primary-800"
            >
              Ver clientes
            </Link>
          </div>
          <div className="divide-y divide-slate-100 px-5">
            {!canSeeCRM ? (
              <div className="py-10 text-center text-sm text-slate-400">
                Conteúdo restrito aos perfis autorizados.
              </div>
            ) : loading ? (
              <div className="space-y-3 py-5">
                {[1, 2, 3, 4].map((item) => (
                  <div
                    key={item}
                    className="h-12 animate-pulse rounded-xl bg-slate-100"
                  />
                ))}
              </div>
            ) : services.length === 0 ? (
              <div className="py-10 text-center text-sm text-slate-400">
                Nenhuma solicitação pendente.
              </div>
            ) : (
              services.slice(0, 5).map((service) => (
                <Link
                  key={service.id}
                  to={`/clientes/${service.client_id}?tab=atendimentos`}
                  className="flex gap-3 py-3.5"
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-600">
                    <MessageSquare className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-1 block text-sm font-semibold text-slate-900">
                      {service.solicitacao || service.resumo || "Atendimento registrado"}
                    </span>
                    <span className="mt-0.5 block text-xs text-slate-500">
                      {service.solicitacao_atrasada
                        ? "Solicitação atrasada"
                        : `Prioridade ${service.solicitacao_prioridade || "normal"}`}
                    </span>
                  </span>
                  <span className="shrink-0 text-[10px] text-slate-400">
                    {formatTime(service.data_atendimento)}
                  </span>
                </Link>
              ))
            )}
          </div>
        </div>

        <div className="option-one-panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
            <div>
              <h2 className="text-base font-semibold">Casos que exigem atenção</h2>
              <p className="mt-0.5 text-xs text-slate-500">
                Risco elevado ou marcação de acompanhamento
              </p>
            </div>
            <Link
              to="/casos"
              className="text-xs font-semibold text-primary-800"
            >
              Ver todos
            </Link>
          </div>
          <div className="divide-y divide-slate-100 px-5">
            {loading ? (
              <div className="space-y-3 py-5">
                {[1, 2, 3, 4].map((item) => (
                  <div
                    key={item}
                    className="h-12 animate-pulse rounded-xl bg-slate-100"
                  />
                ))}
              </div>
            ) : attentionCases.length === 0 ? (
              <div className="py-10 text-center text-sm text-slate-400">
                Nenhum caso marcado com risco elevado.
              </div>
            ) : (
              attentionCases.map((item) => (
                <Link
                  key={item.id}
                  to={`/casos/${item.id}`}
                  className="flex items-center gap-3 py-3.5"
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-800">
                    <Gavel className="h-4 w-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold text-slate-900">
                      {item.titulo || item.nome || item.numero_processo || "Caso sem título"}
                    </span>
                    <span className="mt-0.5 block truncate text-xs capitalize text-slate-500">
                      {item.area || item.fase || "Área não informada"}
                    </span>
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-1 text-[10px] font-semibold text-red-700">
                    <AlertTriangle className="h-3 w-3" />
                    Risco alto
                  </span>
                </Link>
              ))
            )}
          </div>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="option-one-panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
            <div>
              <h2 className="text-base font-semibold">Movimentações recentes</h2>
              <p className="mt-0.5 text-xs text-slate-500">
                Histórico operacional da carteira
              </p>
            </div>
            <Link
              to="/casos"
              className="text-xs font-semibold text-primary-800"
            >
              Abrir carteira
            </Link>
          </div>
          <div className="divide-y divide-slate-100 px-5">
            {loading ? (
              <div className="space-y-3 py-5">
                {[1, 2, 3, 4].map((item) => (
                  <div
                    key={item}
                    className="h-12 animate-pulse rounded-xl bg-slate-100"
                  />
                ))}
              </div>
            ) : movements.length === 0 ? (
              <div className="py-10 text-center text-sm text-slate-400">
                Nenhuma movimentação recente.
              </div>
            ) : (
              movements.slice(0, 6).map((movement, index) => (
                <div
                  key={movement.id || `${movement.tipo}-${index}`}
                  className="flex items-start gap-3 py-3.5"
                >
                  <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-700">
                    <Clock className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="line-clamp-1 text-sm font-semibold text-slate-900">
                      {movement.titulo || movement.descricao || movement.tipo || "Movimentação"}
                    </div>
                    <div className="mt-0.5 text-xs text-slate-500">
                      {formatDate(movement.data || movement.created_at)}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <NoticiasCard />
      </section>
    </div>
  );
}
