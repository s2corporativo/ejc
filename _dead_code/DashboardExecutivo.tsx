import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  TrendingUp, TrendingDown, AlertTriangle, CheckCircle2,
  Briefcase, Wallet, Scale, Users, ArrowRight, Clock,
  Activity, Target, Zap,
} from "lucide-react";
import api from "../lib/api";
import { Spinner, fmtMoney, fmtDate } from "../components/UI";

// ── Donut SVG puro ──────────────────────────────────────────────────────────
function Donut({
  segments, total, label,
}: { segments: { value: number; color: string; label: string }[]; total: number; label: string }) {
  const r = 64, sw = 18, c = 2 * Math.PI * r;
  let acc = 0;
  return (
    <div className="relative flex-shrink-0" style={{ width: 164, height: 164 }}>
      <svg viewBox="0 0 164 164" width={164} height={164} style={{ transform: "rotate(-90deg)" }}>
        <circle cx="82" cy="82" r={r} fill="none" stroke="#F3EEE7" strokeWidth={sw} />
        {total > 0 && segments.map((s, i) => {
          const len = (s.value / total) * c;
          const off = -acc; acc += len;
          return (
            <circle key={i} cx="82" cy="82" r={r} fill="none"
              stroke={s.color} strokeWidth={sw} strokeLinecap="butt"
              strokeDasharray={`${len - 1} ${c - len + 1}`}
              strokeDashoffset={off} />
          );
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-serif text-4xl font-bold text-navy leading-none">{total}</span>
        <span className="text-[10px] uppercase tracking-[0.14em] text-slate-400 mt-1">{label}</span>
      </div>
    </div>
  );
}

// ── Mini barra horizontal ────────────────────────────────────────────────────
function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  return (
    <div className="flex-1 h-1.5 rounded-full overflow-hidden bg-slate-100">
      <div className="h-full rounded-full" style={{ width: `${max > 0 ? (value / max) * 100 : 0}%`, background: color }} />
    </div>
  );
}

// ── KPI Card ─────────────────────────────────────────────────────────────────
function KpiCard({
  label, value, sub, icon: Icon, tone = "text-navy", alert = false, to,
}: {
  label: string; value: string; sub?: string;
  icon: any; tone?: string; alert?: boolean; to?: string;
}) {
  const cls = `card p-5 flex flex-col gap-3 hover:shadow-card-hover hover:-translate-y-0.5 transition-all ${alert ? "ring-1 ring-red-200 bg-red-50/30" : ""}`;
  const inner = (
    <>
      <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${alert ? "bg-red-100" : "bg-bronze-50"}`}>
        <Icon size={17} className={alert ? "text-red-500" : "text-bronze-deep"} />
      </div>
      <div>
        <div className={`text-3xl font-serif font-bold leading-none ${tone}`}>{value}</div>
        <div className="text-[11px] text-slate-400 font-medium uppercase tracking-wide mt-1.5">{label}</div>
        {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
      </div>
    </>
  );
  if (to) return <Link to={to} className={cls}>{inner}</Link>;
  return <div className={cls}>{inner}</div>;
}

// ── Section wrapper ──────────────────────────────────────────────────────────
function Section({ title, sub, action, children }: {
  title: string; sub?: string; action?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="font-serif font-semibold text-navy">{title}</h3>
          {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

const verLink = (to: string, txt = "Ver todos") => (
  <Link to={to} className="text-xs font-semibold text-bronze hover:text-bronze-dark inline-flex items-center gap-1 shrink-0">
    {txt} <ArrowRight size={12} />
  </Link>
);

// ── Pct delta chip ────────────────────────────────────────────────────────────
function Delta({ v }: { v?: number }) {
  if (v == null) return null;
  const up = v >= 0;
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-semibold ${up ? "text-emerald-600" : "text-red-500"}`}>
      {up ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
      {up ? "+" : ""}{v}%
    </span>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function DashboardExecutivo() {
  const [d, setD] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [rent, setRent] = useState<any>(null);
  const [juri, setJuri] = useState<any>(null);
  const [equipe, setEquipe] = useState<any[]>([]);
  const [andamentos, setAndamentos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([
      api.get("/dashboard/"),
      api.get("/analytics/case-health"),
      api.get("/analytics/rentabilidade"),
      api.get("/jurimetria/overview"),
      api.get("/atendimentos/dashboard"),
      api.get("/movimentos/recentes?limit=8"),
    ]).then(([a, b, c, e, f, g]) => {
      if (a.status === "fulfilled") setD(a.value.data);
      if (b.status === "fulfilled") setHealth(b.value.data);
      if (c.status === "fulfilled") setRent(c.value.data);
      if (e.status === "fulfilled") setJuri(e.value.data);
      if (f.status === "fulfilled") setEquipe(f.value.data ?? []);
      if (g.status === "fulfilled") setAndamentos(g.value.data ?? []);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center py-20"><Spinner /></div>;

  // Saúde
  const dist = health?.distribuicao ?? {};
  const healthSegs = [
    { label: "Saudável",  value: dist.saudavel ?? 0, color: "#1D9E75" },
    { label: "Atenção",   value: dist.atencao  ?? 0, color: "#F59E0B" },
    { label: "Risco",     value: dist.risco    ?? 0, color: "#F97316" },
    { label: "Crítico",   value: dist.critico  ?? 0, color: "#EF4444" },
  ];
  const totalH = healthSegs.reduce((s, x) => s + x.value, 0);

  // Financeiro
  const cons = rent?.consolidado ?? {};
  const margemOk = (cons.margem_pct ?? 0) >= 30;

  // Jurimetria
  const taxa = juri?.taxa_sucesso_geral;
  const taxaStr = taxa != null ? `${Math.round(taxa * 100)}%` : "—";

  // Equipe
  const maxAtend = Math.max(1, ...equipe.map((e) => e.total_atendimentos));

  // Casos em risco
  const casosRisco = (health?.casos ?? []).filter((c: any) => !c.saudavel);

  // Alertas críticos
  const alertas = [
    d?.prazos?.vencidos > 0 && { tipo: "danger", msg: `${d.prazos.vencidos} prazo(s) vencido(s)`, to: "/prazos" },
    d?.prazos?.criticos_3d > 0 && { tipo: "warn", msg: `${d.prazos.criticos_3d} prazo(s) nos próximos 3 dias`, to: "/prazos" },
    d?.pecas_aguardando_revisao > 0 && { tipo: "warn", msg: `${d.pecas_aguardando_revisao} peça(s) aguardando revisão HITL`, to: "/pecas" },
    casosRisco.length > 0 && { tipo: "warn", msg: `${casosRisco.length} caso(s) em atenção/risco/crítico`, to: "/casos" },
  ].filter(Boolean) as { tipo: string; msg: string; to: string }[];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.15em] text-bronze mb-1">Visão executiva</p>
          <h1 className="font-serif text-3xl font-bold text-navy">Dashboard Executivo</h1>
          <p className="text-sm text-slate-400 mt-1">Operação · Saúde da carteira · Financeiro · Desempenho da equipe</p>
        </div>
        <div className="text-right hidden md:block">
          <p className="text-xs text-slate-400">Score médio da carteira</p>
          <p className="font-serif text-4xl font-bold text-bronze-deep">{health?.score_medio ?? "—"}</p>
        </div>
      </div>

      {/* Alertas */}
      {alertas.length > 0 && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {alertas.map((al, i) => (
            <Link key={i} to={al.to}
              className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium transition-all hover:scale-[1.01] ${
                al.tipo === "danger" ? "bg-red-50 text-red-700 border border-red-200" : "bg-amber-50 text-amber-700 border border-amber-200"
              }`}>
              <AlertTriangle size={15} className="shrink-0" />
              <span className="truncate">{al.msg}</span>
            </Link>
          ))}
          {alertas.length === 0 && (
            <div className="col-span-4 flex items-center gap-2 text-emerald-600 text-sm bg-emerald-50 rounded-xl px-4 py-3 border border-emerald-200">
              <CheckCircle2 size={15} /> Sem alertas críticos no momento
            </div>
          )}
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard label="Casos ativos" value={String(d?.casos?.ativos ?? "—")}
          sub={`${d?.clientes_ativos ?? 0} clientes ativos`} icon={Briefcase} to="/casos" />
        <KpiCard label="A receber" value={fmtMoney(d?.financeiro?.pendente ?? 0)}
          sub={`Recebido: ${fmtMoney(d?.financeiro?.recebido_mes ?? 0)}`} icon={Wallet} to="/honorarios" />
        <KpiCard label="Taxa de sucesso" value={taxaStr}
          sub={juri ? `${juri.venceu ?? 0}V · ${juri.perdeu ?? 0}D · ${juri.acordo ?? 0} acordos` : "Sem dados"}
          icon={Scale} tone="text-bronze-deep" />
        <KpiCard label="Prazos vencidos" value={String(d?.prazos?.vencidos ?? 0)}
          sub={`${d?.prazos?.criticos_3d ?? 0} críticos · ${d?.prazos?.proximos_7d ?? 0} em 7d`}
          icon={Clock} alert={(d?.prazos?.vencidos ?? 0) > 0} tone="text-red-700" to="/prazos" />
      </div>

      {/* Saúde + Financeiro */}
      <div className="grid lg:grid-cols-5 gap-6">
        {/* Saúde da carteira — 3/5 */}
        <Section title="Saúde da carteira"
          sub={`${totalH} casos monitorados`}
          action={<Delta v={health?.variacao_mes} />}
          // @ts-ignore
          className="lg:col-span-3">
          <div className="lg:col-span-3 card p-6">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h3 className="font-serif font-semibold text-navy">Saúde da carteira</h3>
                <p className="text-xs text-slate-400 mt-0.5">{totalH} casos monitorados</p>
              </div>
              <Delta v={health?.variacao_mes} />
            </div>
            <div className="flex items-center gap-8">
              <Donut segments={healthSegs} total={totalH} label="casos" />
              <div className="flex-1 space-y-3">
                {healthSegs.map((s) => (
                  <div key={s.label}>
                    <div className="flex items-center justify-between text-sm mb-1.5">
                      <span className="flex items-center gap-2 text-slate-600 font-medium">
                        <span className="w-2 h-2 rounded-full" style={{ background: s.color }} />{s.label}
                      </span>
                      <span className="font-bold text-navy">{s.value}
                        <span className="font-normal text-slate-400 text-xs ml-1">
                          ({totalH > 0 ? Math.round((s.value / totalH) * 100) : 0}%)
                        </span>
                      </span>
                    </div>
                    <Bar value={s.value} max={totalH} color={s.color} />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Section>

        {/* Financeiro — 2/5 */}
        <div className="lg:col-span-2 card p-6 flex flex-col">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h3 className="font-serif font-semibold text-navy">Financeiro</h3>
              <p className="text-xs text-slate-400 mt-0.5">Consolidado do mês</p>
            </div>
            {verLink("/honorarios")}
          </div>
          <div className="flex-1 space-y-4">
            {[
              { l: "Receita recebida",  v: fmtMoney(cons.receita_recebida ?? d?.financeiro?.recebido_mes ?? 0), c: "text-emerald-600" },
              { l: "Custo (horas)",     v: fmtMoney(cons.custo_horas ?? 0),   c: "text-slate-700" },
              { l: "Lucro estimado",    v: fmtMoney(cons.lucro ?? 0),         c: (cons.lucro ?? 0) >= 0 ? "text-emerald-600" : "text-red-500" },
              { l: "Inadimplência",     v: fmtMoney(d?.financeiro?.atrasado ?? 0), c: "text-red-500" },
            ].map(({ l, v, c }) => (
              <div key={l} className="flex justify-between items-center border-b border-bronze-50 pb-3 last:border-0 last:pb-0">
                <span className="text-sm text-slate-500">{l}</span>
                <span className={`text-sm font-bold ${c}`}>{v}</span>
              </div>
            ))}
          </div>
          {/* Margem pill */}
          <div className={`mt-5 rounded-xl px-4 py-3 flex items-center gap-2 ${margemOk ? "bg-emerald-50" : "bg-amber-50"}`}>
            {margemOk ? <TrendingUp size={16} className="text-emerald-600" /> : <Activity size={16} className="text-amber-600" />}
            <div>
              <p className={`text-sm font-bold ${margemOk ? "text-emerald-700" : "text-amber-700"}`}>
                Margem {cons.margem_pct != null ? `${cons.margem_pct}%` : "—"}
              </p>
              <p className="text-xs text-slate-400">{rent?.nota ?? "Rentabilidade calculada com base nas horas faturadas"}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Performance da equipe + Jurimetria */}
      <div className="grid lg:grid-cols-5 gap-6">
        {/* Equipe — 3/5 */}
        <div className="lg:col-span-3 card p-6">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h3 className="font-serif font-semibold text-navy">Performance da equipe</h3>
              <p className="text-xs text-slate-400 mt-0.5">Atendimentos por advogado responsável</p>
            </div>
            {verLink("/atendimentos")}
          </div>
          {equipe.length === 0 ? (
            <div className="flex flex-col items-center py-8 text-slate-400">
              <Users size={28} className="mb-2 opacity-40" />
              <p className="text-sm">Nenhum atendimento registrado</p>
            </div>
          ) : (
            <div className="space-y-4">
              {equipe.slice(0, 6).map((e, i) => (
                <div key={e.advogado_id ?? i} className="flex items-center gap-3">
                  {/* Avatar */}
                  <div className="w-8 h-8 rounded-full bg-navy/10 flex items-center justify-center shrink-0">
                    <span className="text-xs font-bold text-navy">
                      {(e.nome ?? e.advogado_id ?? "?")[0].toUpperCase()}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-slate-700 truncate">
                        {e.nome ?? e.advogado_id?.slice(0, 8) ?? "Advogado"}
                      </span>
                      <div className="flex items-center gap-3 shrink-0 ml-2">
                        <span className="text-xs text-slate-400">{e.total_horas}h</span>
                        <span className="text-sm font-bold text-navy">{e.total_atendimentos}</span>
                      </div>
                    </div>
                    <Bar value={e.total_atendimentos} max={maxAtend} color="#AA8660" />
                  </div>
                  {/* Satisfação */}
                  {e.satisfacao_media > 0 && (
                    <div className="shrink-0 text-right">
                      <span className="text-xs font-semibold text-bronze-deep">★ {e.satisfacao_media.toFixed(1)}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Jurimetria — 2/5 */}
        <div className="lg:col-span-2 card p-6 flex flex-col">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h3 className="font-serif font-semibold text-navy">Jurimetria</h3>
              <p className="text-xs text-slate-400 mt-0.5">Desempenho processual</p>
            </div>
            {verLink("/jurimetria")}
          </div>
          {/* Taxa de sucesso — donut small */}
          <div className="flex items-center gap-4 mb-6">
            <div className="relative w-20 h-20 shrink-0">
              <svg viewBox="0 0 80 80" width={80} height={80} style={{ transform: "rotate(-90deg)" }}>
                <circle cx="40" cy="40" r="30" fill="none" stroke="#F3EEE7" strokeWidth={10} />
                {taxa != null && (
                  <circle cx="40" cy="40" r="30" fill="none" stroke="#1D9E75" strokeWidth={10}
                    strokeDasharray={`${taxa * 2 * Math.PI * 30} ${(1 - taxa) * 2 * Math.PI * 30}`}
                    strokeLinecap="butt" />
                )}
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="font-serif font-bold text-lg text-navy">{taxaStr}</span>
              </div>
            </div>
            <div className="text-sm">
              <p className="text-slate-400 text-xs mb-2">Processos encerrados</p>
              <div className="space-y-1">
                <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-emerald-500" /><span className="text-slate-600">Vitórias <b className="text-navy">{juri?.venceu ?? 0}</b></span></div>
                <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-red-400" /><span className="text-slate-600">Derrotas <b className="text-navy">{juri?.perdeu ?? 0}</b></span></div>
                <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-amber-400" /><span className="text-slate-600">Acordos <b className="text-navy">{juri?.acordo ?? 0}</b></span></div>
              </div>
            </div>
          </div>
          {/* Stats */}
          <div className="flex-1 grid grid-cols-2 gap-3">
            {[
              { l: "Tempo médio", v: juri?.tempo_medio_dias ? `${juri.tempo_medio_dias}d` : "—", icon: Clock },
              { l: "Processos ativos", v: String(juri?.ativos ?? d?.casos?.ativos ?? "—"), icon: Target },
              { l: "Valor em causa", v: fmtMoney(juri?.valor_total_causa), icon: Wallet },
              { l: "Êxito esperado", v: juri?.exito_medio ? `${Math.round(juri.exito_medio * 100)}%` : "—", icon: Zap },
            ].map(({ l, v, icon: Icon }) => (
              <div key={l} className="rounded-xl bg-bronze-50 p-3">
                <Icon size={14} className="text-bronze mb-1" />
                <p className="font-bold text-navy text-sm">{v}</p>
                <p className="text-[10px] text-slate-400 uppercase tracking-wide">{l}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Casos em risco + Andamentos recentes */}
      <div className="grid lg:grid-cols-2 gap-6">
        <Section title="Casos que exigem atenção" sub={`${casosRisco.length} caso(s) monitorados`} action={verLink("/casos")}>
          {casosRisco.length === 0 ? (
            <div className="flex flex-col items-center py-8 text-slate-400">
              <CheckCircle2 size={28} className="mb-2 text-emerald-400" />
              <p className="text-sm text-emerald-600 font-medium">Carteira saudável!</p>
            </div>
          ) : (
            <div className="space-y-2">
              {casosRisco.slice(0, 7).map((c: any) => {
                const cls: Record<string, string> = {
                  critico: "bg-red-100 text-red-700 border-red-200",
                  risco:   "bg-orange-100 text-orange-700 border-orange-200",
                  atencao: "bg-amber-100 text-amber-700 border-amber-200",
                };
                const st = cls[c.classificacao] ?? cls.atencao;
                return (
                  <Link key={c.case_id} to={`/casos/${c.case_id}`}
                    className="flex items-center justify-between gap-2 p-3 rounded-xl border border-bronze-50 hover:bg-bronze-50/50 transition-colors">
                    <div className="min-w-0">
                      <p className="text-sm text-slate-700 truncate font-medium">
                        {c.numero_interno ? `[${c.numero_interno}] ` : ""}{c.titulo}
                      </p>
                    </div>
                    <span className={`shrink-0 text-[11px] font-bold px-2.5 py-1 rounded-full border ${st}`}>
                      {c.classificacao} · {c.score}
                    </span>
                  </Link>
                );
              })}
            </div>
          )}
        </Section>

        <Section title="Andamentos recentes" action={verLink("/casos")}>
          {andamentos.length === 0 ? (
            <p className="text-sm text-slate-400 py-8 text-center">Sem movimentações recentes.</p>
          ) : (
            <div className="space-y-1">
              {andamentos.map((m: any) => {
                const chips: Record<string, string> = {
                  peticao:    "bg-sky-100 text-sky-700",
                  decisao:    "bg-purple-100 text-purple-700",
                  audiencia:  "bg-amber-100 text-amber-700",
                  intimacao:  "bg-red-100 text-red-700",
                  ia:         "bg-bronze-50 text-bronze-deep",
                  nota:       "bg-slate-100 text-slate-600",
                  encerramento: "bg-emerald-100 text-emerald-700",
                };
                const chip = chips[m.tipo] ?? "bg-slate-100 text-slate-600";
                return (
                  <Link key={m.id} to={`/casos/${m.case_id}`}
                    className="flex items-start gap-3 py-2.5 px-2 -mx-2 rounded-xl hover:bg-bronze-50/50 transition-colors">
                    <span className={`shrink-0 mt-0.5 text-[10px] font-bold px-2 py-0.5 rounded-full ${chip}`}>{m.tipo}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-slate-700 truncate">{m.descricao}</p>
                      <p className="text-xs text-slate-400">{m.case_titulo}</p>
                    </div>
                    <span className="shrink-0 text-xs text-slate-400">{fmtDate(m.quando)}</span>
                  </Link>
                );
              })}
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}
