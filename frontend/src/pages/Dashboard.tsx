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
  civil: "bg-primary-500",
  trabalhista: "bg-ai-500",
  consumidor: "bg-warn-400",
  familia: "bg-primary-300",
  ambiental: "bg-success-500",
  criminal: "bg-danger-500",
  previdenciario: "bg-warn-500",
  empresarial: "bg-primary-700",
  tributario: "bg-info-600",
};

// Paleta do donut — marrom profundo / bronze / dourado / creme (mockup).
// Via CSS vars: no escuro o marrom (invisível sobre #1C1712) troca com o
// creme — ver --ejc-chart-* em index.css.
const DONUT_COLORS = [
  "var(--ejc-chart-1)",
  "var(--ejc-chart-2)",
  "var(--ejc-chart-3)",
  "var(--ejc-chart-4)",
  "var(--ejc-chart-5)",
  "var(--ejc-chart-6)",
];

function initials(value?: string) {
  return (value || "?")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((x) => x[0])
    .join("")
    .toUpperCase();
}

/** Gráfico de área dourado com fill gradiente (SVG puro — sem lib externa). */
function GoldAreaChart({
  points,
}: {
  points: Array<{ label: string; value: number }>;
}) {
  const W = 600;
  const H = 200;
  const PAD = 24;
  const max = Math.max(1, ...points.map((p) => p.value));
  const stepX = points.length > 1 ? (W - PAD * 2) / (points.length - 1) : 0;
  const coords = points.map((p, i) => ({
    x: PAD + i * stepX,
    y: H - PAD - (p.value / max) * (H - PAD * 2),
  }));
  const line = coords
    .map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`)
    .join(" ");
  const area = `${line} L${(PAD + (points.length - 1) * stepX).toFixed(1)},${H - PAD} L${PAD},${H - PAD} Z`;
  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-48 w-full"
        preserveAspectRatio="none"
        role="img"
        aria-label="Evolucao de prazos"
      >
        <defs>
          <linearGradient id="gold-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#D4AF37" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#D4AF37" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {/* grid segue o tema (claro: cinza; escuro: creme translúcido) */}
        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1={PAD}
            x2={W - PAD}
            y1={PAD + f * (H - PAD * 2)}
            y2={PAD + f * (H - PAD * 2)}
            className="stroke-slate-100 dark:stroke-[rgba(255,245,230,0.09)]"
            strokeWidth="1"
          />
        ))}
        {points.length > 1 && (
          <>
            <path d={area} fill="url(#gold-fill)" />
            <path
              d={line}
              fill="none"
              stroke="#D4AF37"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </>
        )}
        {coords.map((c, i) => (
          <circle
            key={i}
            cx={c.x}
            cy={c.y}
            r="3.5"
            fill="var(--ejc-card)"
            stroke="#D4AF37"
            strokeWidth="2"
          />
        ))}
      </svg>
      <div className="mt-1 flex justify-between px-1 text-[10px] font-medium text-slate-400">
        {points.map((p) => (
          <span key={p.label}>{p.label}</span>
        ))}
      </div>
    </div>
  );
}

/** Donut SVG dourado/âmbar/laranja (sem lib externa). */
function DonutChart({
  slices,
}: {
  slices: Array<{ label: string; value: number; color: string }>;
}) {
  const total = slices.reduce((acc, s) => acc + s.value, 0) || 1;
  const R = 42;
  const C = 2 * Math.PI * R;
  let offset = 0;
  return (
    <div className="flex items-center gap-5">
      <svg viewBox="0 0 120 120" className="h-32 w-32 shrink-0 -rotate-90">
        <circle
          cx="60"
          cy="60"
          r={R}
          fill="none"
          className="stroke-slate-100 dark:stroke-[rgba(255,245,230,0.09)]"
          strokeWidth="14"
        />
        {slices.map((s) => {
          const frac = s.value / total;
          const dash = `${frac * C} ${C}`;
          const el = (
            <circle
              key={s.label}
              cx="60"
              cy="60"
              r={R}
              fill="none"
              stroke={s.color}
              strokeWidth="14"
              strokeDasharray={dash}
              strokeDashoffset={-offset * C}
              strokeLinecap="butt"
            />
          );
          offset += frac;
          return el;
        })}
      </svg>
      <div className="min-w-0 flex-1 space-y-2">
        {slices.slice(0, 6).map((s) => (
          <div
            key={s.label}
            className="flex items-center gap-2 text-xs text-slate-600"
          >
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: s.color }}
            />
            <span className="min-w-0 flex-1 truncate capitalize">
              {s.label}
            </span>
            <span className="font-semibold tabular-nums text-slate-900">
              {s.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
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
      api.get("/cases/?page_size=200"),
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
  const honorariosPendentes =
    dashboard?.financeiro?.pendente ??
    dashboard?.financeiro?.honorarios_pendentes;
  const receitaMes =
    dashboard?.financeiro?.honorarios_mes ?? dashboard?.financeiro?.receita_mes;

  // Série do gráfico principal: prazos pendentes por semana (próximas 6)
  const serieSemanas = useMemo(() => {
    const buckets = [0, 0, 0, 0, 0, 0];
    // Inicio do dia: um prazo que vence HOJE conta em "Esta sem." mesmo apos
    // meio-dia; prazos pendentes ja vencidos tambem entram no bucket 0.
    const hoje = new Date();
    hoje.setHours(0, 0, 0, 0);
    for (const p of prazos) {
      if (!p.data_prazo) continue;
      const d = new Date(
        String(p.data_prazo).includes("T")
          ? p.data_prazo
          : p.data_prazo + "T12:00:00",
      );
      const diff = Math.floor(
        (d.getTime() - hoje.getTime()) / (7 * 24 * 3600 * 1000),
      );
      if (diff < 6) buckets[Math.max(diff, 0)] += 1;
    }
    return buckets.map((v, i) => ({
      label: i === 0 ? "Esta sem." : `+${i} sem.`,
      value: v,
    }));
  }, [prazos]);

  // Donut: distribuição da carteira por área do direito
  const areasDonut = useMemo(() => {
    const count = new Map<string, number>();
    for (const c of casos) {
      const area = (c.area || "outros").toLowerCase();
      count.set(area, (count.get(area) || 0) + 1);
    }
    return Array.from(count.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([label, value], i) => ({
        label,
        value,
        color: DONUT_COLORS[i % DONUT_COLORS.length],
      }));
  }, [casos]);

  const recebido = typeof receitaMes === "number" ? receitaMes : 0;
  const pendente =
    typeof honorariosPendentes === "number" ? honorariosPendentes : 0;
  const pctRecebido =
    recebido + pendente > 0
      ? Math.round((recebido / (recebido + pendente)) * 100)
      : 0;

  const quickActions = [
    { to: "/casos", label: "Novo caso", icon: Plus },
    { to: "/clientes", label: "Novo cliente", icon: Users },
    { to: "/pecas", label: "Gerar peca", icon: FileText },
    { to: "/casos?filtro=ativos", label: "Sala de Guerra", icon: Gavel },
    { to: "/inteligencia", label: "Radar de Poder", icon: Sparkles },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <PageHeader
          eyebrow="Painel executivo"
          title={`Bom trabalho, ${nome}`}
          subtitle="Visao consolidada do escritorio: casos, prazos, financeiro, produtividade e inteligencia juridica."
        />
        <div className="mb-6 flex flex-wrap gap-2">
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

      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
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
          value={prazosCriticos}
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
          trend={recebido > 0 ? "up" : undefined}
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
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <SectionCard
          title="Prazos das proximas semanas"
          subtitle="Volume de prazos pendentes por semana."
          actions={
            <Link
              to="/prazos"
              className="text-sm font-medium text-primary-600 hover:text-primary-700"
            >
              Ver prazos
            </Link>
          }
        >
          {loading ? (
            <div className="h-48 animate-pulse rounded-xl bg-slate-100" />
          ) : (
            <GoldAreaChart points={serieSemanas} />
          )}
        </SectionCard>

        <div className="space-y-5">
          <SectionCard
            title="Carteira por area"
            subtitle="Distribuicao dos casos."
          >
            {areasDonut.length === 0 ? (
              <EmptyState title="Sem casos" icon={Briefcase} />
            ) : (
              <DonutChart slices={areasDonut} />
            )}
          </SectionCard>

          <SectionCard title="Honorarios" subtitle="Recebido vs. a receber.">
            <div className="flex items-end justify-between">
              <div className="text-2xl font-semibold tracking-tight text-slate-950 tabular-nums">
                {pctRecebido}%
              </div>
              <div className="text-xs text-slate-400">
                {fmtMoney(recebido)} de {fmtMoney(recebido + pendente)}
              </div>
            </div>
            <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-gradient-to-r from-ai-400 to-primary-500 transition-all"
                style={{ width: `${pctRecebido}%` }}
              />
            </div>
            <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-400">
              <CheckCircle2 className="h-3.5 w-3.5 text-success-600" />
              Meta: converter pendencias do mes em receita.
            </div>
          </SectionCard>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
        <SectionCard
          title="Agenda de hoje e prazos proximos"
          subtitle="Itens que merecem atencao imediata."
          actions={
            <Link
              to="/atividades"
              className="text-sm font-medium text-primary-600 hover:text-primary-700"
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
          actions={<Sparkles className="h-4 w-4 text-ai-600" />}
        >
          <div className="space-y-3">
            <div className="rounded-xl border border-danger-100 bg-danger-50 p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 h-4 w-4 text-danger-600" />
                <div>
                  <div className="text-sm font-semibold text-danger-800">
                    {prazosCriticos} prazo(s) critico(s)
                  </div>
                  <p className="mt-1 text-xs text-danger-700">
                    Priorize prazos com vencimento em ate 3 dias.
                  </p>
                </div>
              </div>
            </div>
            <div className="rounded-xl border border-ai-100 bg-ai-50 p-4">
              <div className="flex items-start gap-3">
                <Bot className="mt-0.5 h-4 w-4 text-ai-700" />
                <div>
                  <div className="text-sm font-semibold text-ai-900">
                    IA juridica disponivel
                  </div>
                  <p className="mt-1 text-xs text-ai-800">
                    Rascunhos, analise de risco e apoio a producao sempre exigem
                    revisao humana.
                  </p>
                </div>
              </div>
            </div>
            <Link
              to="/financeiro"
              className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4 text-sm font-medium text-slate-700 hover:border-primary-200 hover:bg-primary-50"
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
              className="text-sm font-medium text-primary-600 hover:text-primary-700"
            >
              Ver casos
            </Link>
          }
        >
          {casos.length === 0 ? (
            <EmptyState title="Sem casos recentes" icon={Briefcase} />
          ) : (
            <div className="space-y-3">
              {casos.slice(0, 6).map((caso) => (
                <Link
                  key={caso.id}
                  to={`/casos/${caso.id}`}
                  className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 hover:border-primary-200 hover:bg-primary-50/40"
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
              className="text-sm font-medium text-primary-600 hover:text-primary-700"
            >
              Inteligencia
            </Link>
          }
        >
          <div className="mb-4 grid grid-cols-3 gap-3">
            <div className="rounded-xl bg-slate-50 p-3 text-center">
              <BarChart3 className="mx-auto h-4 w-4 text-primary-600" />
              <div className="mt-2 text-lg font-semibold text-slate-950">
                {taxaExito != null ? `${taxaExito}%` : "—"}
              </div>
              <div className="text-[11px] text-slate-500">Exito</div>
            </div>
            <div className="rounded-xl bg-slate-50 p-3 text-center">
              <Scale className="mx-auto h-4 w-4 text-ai-600" />
              <div className="mt-2 text-lg font-semibold text-slate-950">
                {jurimetria?.total_casos ?? "—"}
              </div>
              <div className="text-[11px] text-slate-500">Casos</div>
            </div>
            <div className="rounded-xl bg-slate-50 p-3 text-center">
              <Gavel className="mx-auto h-4 w-4 text-success-600" />
              <div className="mt-2 text-lg font-semibold text-slate-950">
                {movimentos.length}
              </div>
              <div className="text-[11px] text-slate-500">
                Andamentos recentes
              </div>
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
                tone: "text-primary-700 bg-primary-50 border-primary-100",
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
                tone: "text-ai-700 bg-ai-50 border-ai-100",
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
