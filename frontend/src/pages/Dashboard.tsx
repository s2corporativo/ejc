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
  Search,
  Sparkles,
  Users,
  Wallet,
} from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../stores/auth";
import {
  Badge,
  Button,
  EmptyState,
  PageHeader,
  SectionCard,
  StatCard,
  StatusBadge,
  fmtDate,
  fmtMoney,
} from "../components/UI";
import NoticiasCard from "../components/NoticiasCard";

const areaTone: Record<string, string> = {
  civil: "bg-blue-600",
  trabalhista: "bg-violet-600",
  consumidor: "bg-cyan-600",
  familia: "bg-pink-600",
  ambiental: "bg-emerald-600",
  criminal: "bg-red-600",
  previdenciario: "bg-amber-600",
  empresarial: "bg-blue-700",
  tributario: "bg-sky-700",
};

function initials(value?: string) {
  return (value || "?")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((x) => x[0])
    .join("")
    .toUpperCase();
}

export default function Dashboard() {
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
      api.get("/movimentos/recentes?limit=6"),
      api.get("/cases/?page_size=6"),
    ])
      .then(([dash, juri, deadlines, movs, cases]) => {
        if (dash.status === "fulfilled") setDashboard(dash.value.data);
        if (juri.status === "fulfilled") setJurimetria(juri.value.data);
        if (deadlines.status === "fulfilled")
          setPrazos(
            deadlines.value.data?.data ?? deadlines.value.data?.items ?? [],
          );
        if (movs.status === "fulfilled") setMovimentos(movs.value.data ?? []);
        if (cases.status === "fulfilled")
          setCasos(
            cases.value.data?.data ??
              cases.value.data?.items ??
              cases.value.data ??
              [],
          );
      })
      .finally(() => setLoading(false));
  }, []);

  const nome = (user as any)?.full_name?.split(" ")[0] || "Dr.";
  const taxaExito =
    jurimetria?.taxa_sucesso_geral != null
      ? Math.round(jurimetria.taxa_sucesso_geral * 100)
      : null;
  const prazosOrdenados = useMemo(
    () =>
      [...prazos]
        .sort((a, b) =>
          String(a.data_prazo || "").localeCompare(String(b.data_prazo || "")),
        )
        .slice(0, 6),
    [prazos],
  );
  const prazosCriticos = prazos.filter(
    (p) => (p.dias_restantes ?? 99) <= 3,
  ).length;
  const tarefasAbertas =
    dashboard?.tarefas?.abertas ?? dashboard?.tarefas_abertas ?? "—";
  const honorariosPendentes =
    dashboard?.financeiro?.pendente ??
    dashboard?.financeiro?.honorarios_pendentes;
  const receitaMes =
    dashboard?.financeiro?.honorarios_mes ?? dashboard?.financeiro?.receita_mes;

  const quickActions = [
    { to: "/casos", label: "Novo caso", icon: Plus },
    { to: "/clientes", label: "Novo cliente", icon: Users },
    { to: "/pecas", label: "Gerar peca", icon: FileText },
    { to: "/sala-de-guerra", label: "Sala de Guerra", icon: Gavel },
    { to: "/inteligencia", label: "Radar de Poder", icon: Sparkles },
  ];

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-blue-100 bg-white p-5 shadow-sm md:p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <PageHeader
            eyebrow="Painel executivo"
            title={`Bom trabalho, ${nome}`}
            subtitle="Visao consolidada do escritorio: casos, prazos, financeiro, produtividade e inteligencia juridica."
          />
          <div className="flex flex-wrap gap-2">
            {quickActions.map(({ to, label, icon: Icon }) => (
              <Link key={to} to={to}>
                <Button
                  variant={label === "Novo caso" ? "primary" : "secondary"}
                  icon={<Icon className="h-4 w-4" />}
                >
                  {label}
                </Button>
              </Link>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
        <StatCard
          label="Casos ativos"
          value={dashboard?.casos?.ativos ?? "—"}
          subtitle={
            dashboard?.casos?.total
              ? `${dashboard.casos.total} casos no total`
              : "Carteira atual"
          }
          icon={<Briefcase className="h-5 w-5" />}
          tone="blue"
        />
        <StatCard
          label="Prazos criticos"
          value={prazosCriticos || dashboard?.prazos?.proximos_7d || "—"}
          subtitle="Proximos 3 dias"
          icon={<AlertTriangle className="h-5 w-5" />}
          tone={prazosCriticos ? "red" : "amber"}
          trend={prazosCriticos ? "down" : undefined}
        />
        <StatCard
          label="Receita do mes"
          value={typeof receitaMes === "number" ? fmtMoney(receitaMes) : "—"}
          subtitle="Honorarios recebidos"
          icon={<DollarSign className="h-5 w-5" />}
          tone="green"
        />
        <StatCard
          label="Pendentes"
          value={
            typeof honorariosPendentes === "number"
              ? fmtMoney(honorariosPendentes)
              : "—"
          }
          subtitle="Honorarios a receber"
          icon={<Wallet className="h-5 w-5" />}
          tone="amber"
        />
        <StatCard
          label="Tarefas abertas"
          value={tarefasAbertas}
          subtitle="Operacao juridica"
          icon={<CheckCircle2 className="h-5 w-5" />}
          tone="slate"
        />
        <StatCard
          label="Saude da IA"
          value={taxaExito != null ? `${taxaExito}%` : "OK"}
          subtitle="Jurimetria e apoio"
          icon={<Bot className="h-5 w-5" />}
          tone="purple"
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
        <SectionCard
          title="Agenda de hoje e prazos proximos"
          subtitle="Itens que merecem atencao imediata."
          actions={
            <Link
              to="/atividades"
              className="text-sm font-medium text-blue-600 hover:text-blue-700"
            >
              Abrir central
            </Link>
          }
        >
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-14 animate-pulse rounded-xl bg-slate-100"
                />
              ))}
            </div>
          ) : prazosOrdenados.length === 0 ? (
            <EmptyState
              title="Nenhum prazo pendente"
              message="A agenda operacional esta limpa para os filtros atuais."
              icon={CalendarClock}
            />
          ) : (
            <div className="divide-y divide-slate-100">
              {prazosOrdenados.map((prazo, index) => {
                const dias = prazo.dias_restantes ?? 99;
                const tone = dias <= 0 ? "red" : dias <= 3 ? "amber" : "slate";
                return (
                  <Link
                    key={prazo.id ?? index}
                    to="/atividades"
                    className="flex items-center gap-4 py-3 hover:bg-slate-50"
                  >
                    <div className="flex h-11 w-11 shrink-0 flex-col items-center justify-center rounded-xl border border-slate-200 bg-white">
                      <span className="text-sm font-semibold text-slate-950">
                        {prazo.data_prazo
                          ? new Date(prazo.data_prazo).getDate()
                          : "--"}
                      </span>
                      <span className="text-[10px] uppercase text-slate-400">
                        dia
                      </span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-slate-950">
                        {prazo.titulo || "Prazo sem titulo"}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                        <Clock className="h-3.5 w-3.5" />
                        {fmtDate(prazo.data_prazo)}
                        {prazo.case_title && (
                          <span className="truncate">• {prazo.case_title}</span>
                        )}
                      </div>
                    </div>
                    <Badge tone={tone}>
                      {dias < 0
                        ? "Vencido"
                        : dias === 0
                          ? "Hoje"
                          : `${dias} dias`}
                    </Badge>
                  </Link>
                );
              })}
            </div>
          )}
        </SectionCard>

        <SectionCard
          title="Alertas inteligentes"
          subtitle="Sinais rapidos para decisao."
          actions={<Sparkles className="h-4 w-4 text-violet-600" />}
        >
          <div className="space-y-3">
            <div className="rounded-xl border border-red-100 bg-red-50 p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-4 w-4 text-red-600" />
                <div>
                  <div className="text-sm font-semibold text-red-800">
                    {prazosCriticos} prazo(s) critico(s)
                  </div>
                  <p className="mt-1 text-xs text-red-700">
                    Priorize prazos com vencimento em ate 3 dias.
                  </p>
                </div>
              </div>
            </div>
            <div className="rounded-xl border border-violet-100 bg-violet-50 p-4">
              <div className="flex items-start gap-3">
                <Bot className="mt-0.5 h-4 w-4 text-violet-700" />
                <div>
                  <div className="text-sm font-semibold text-violet-900">
                    IA juridica disponivel
                  </div>
                  <p className="mt-1 text-xs text-violet-800">
                    Rascunhos, analise de risco e apoio a producao sempre exigem
                    revisao humana.
                  </p>
                </div>
              </div>
            </div>
            <div className="rounded-xl border border-emerald-100 bg-emerald-50 p-4">
              <div className="flex items-start gap-3">
                <DollarSign className="mt-0.5 h-4 w-4 text-emerald-700" />
                <div>
                  <div className="text-sm font-semibold text-emerald-900">
                    Auditoria de Honorários
                  </div>
                  <p className="mt-1 text-xs text-emerald-800">
                    Novos ativos recuperáveis identificados. Verifique o módulo financeiro.
                  </p>
                </div>
              </div>
            </div>
            <Link
              to="/financeiro"
              className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4 text-sm font-medium text-slate-700 hover:border-blue-200 hover:bg-blue-50"
            >
              Ver financeiro consolidado
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <SectionCard
          title="Casos recentes"
          subtitle="Carteira ativa para leitura rapida."
          actions={
            <Link
              to="/casos"
              className="text-sm font-medium text-blue-600 hover:text-blue-700"
            >
              Ver casos
            </Link>
          }
        >
          {casos.length === 0 ? (
            <EmptyState title="Sem casos recentes" icon={Briefcase} />
          ) : (
            <div className="space-y-3">
              {casos.map((caso) => (
                <Link
                  key={caso.id}
                  to={`/casos/${caso.id}`}
                  className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 hover:border-blue-200 hover:bg-blue-50/40"
                >
                  <div
                    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-xs font-semibold text-white ${areaTone[caso.area] || "bg-slate-700"}`}
                  >
                    {initials(caso.titulo || caso.numero_interno)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-semibold text-slate-950">
                      {caso.titulo || caso.numero_interno || "Caso sem titulo"}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      {caso.area && <Badge tone="blue">{caso.area}</Badge>}
                      <StatusBadge value={caso.status} />
                    </div>
                  </div>
                  <ArrowRight className="h-4 w-4 text-slate-400" />
                </Link>
              ))}
            </div>
          )}
        </SectionCard>

        <SectionCard
          title="Produtividade e conhecimento"
          subtitle="Movimentacoes, jurimetria e conteudo relevante."
          actions={
            <Link
              to="/inteligencia"
              className="text-sm font-medium text-blue-600 hover:text-blue-700"
            >
              Inteligencia
            </Link>
          }
        >
          <div className="mb-4 grid grid-cols-3 gap-3">
            <div className="rounded-xl bg-slate-50 p-3 text-center">
              <BarChart3 className="mx-auto h-4 w-4 text-blue-600" />
              <div className="mt-2 text-lg font-semibold text-slate-950">
                {taxaExito != null ? `${taxaExito}%` : "—"}
              </div>
              <div className="text-[11px] text-slate-500">Exito</div>
            </div>
            <div className="rounded-xl bg-slate-50 p-3 text-center">
              <Scale className="mx-auto h-4 w-4 text-violet-600" />
              <div className="mt-2 text-lg font-semibold text-slate-950">
                {jurimetria?.total_casos ?? "—"}
              </div>
              <div className="text-[11px] text-slate-500">Casos</div>
            </div>
            <div className="rounded-xl bg-slate-50 p-3 text-center">
              <Gavel className="mx-auto h-4 w-4 text-emerald-600" />
              <div className="mt-2 text-lg font-semibold text-slate-950">
                {movimentos.length}
              </div>
              <div className="text-[11px] text-slate-500">Andamentos</div>
            </div>
          </div>

          <div className="space-y-2">
            {movimentos.slice(0, 4).map((mov, index) => (
              <Link
                key={mov.id ?? index}
                to={mov.case_id ? `/casos/${mov.case_id}` : "/atividades"}
                className="block rounded-lg border border-slate-100 bg-white p-3 hover:bg-slate-50"
              >
                <div className="line-clamp-2 text-sm text-slate-700">
                  {mov.descricao || "Movimento registrado"}
                </div>
                <div className="mt-1 text-xs text-slate-400">
                  {fmtDate(mov.quando || mov.created_at)}
                </div>
              </Link>
            ))}
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <SectionCard
          title="Atalhos de producao"
          subtitle="Fluxos frequentes do escritorio."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              {
                to: "/pecas",
                label: "Producao juridica",
                icon: FileText,
                tone: "text-blue-700 bg-blue-50 border-blue-100",
              },
              {
                to: "/documentos",
                label: "Data Room",
                icon: FolderOpen,
                tone: "text-slate-700 bg-slate-50 border-slate-200",
              },
              {
                to: "/inteligencia",
                label: "IA do escritorio",
                icon: Sparkles,
                tone: "text-violet-700 bg-violet-50 border-violet-100",
              },
              {
                to: "/ramos/administrativo",
                label: "Licitacoes",
                icon: Scale,
                tone: "text-amber-700 bg-amber-50 border-amber-100",
              },
            ].map(({ to, label, icon: Icon, tone }) => (
              <Link
                key={to}
                to={to}
                className={`flex items-center gap-3 rounded-xl border p-4 text-sm font-semibold ${tone}`}
              >
                <Icon className="h-5 w-5" />
                {label}
              </Link>
            ))}
          </div>
        </SectionCard>

        <NoticiasCard />
      </div>
    </div>
  );
}
