import { useEffect, useState, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle, CheckCircle2, Clock, Briefcase, Wallet, Scale,
  Users, ArrowRight, TrendingUp, TrendingDown, Activity,
  CalendarDays, ListTodo, Zap, Target, FileWarning, ChevronRight,
  BookOpen, ExternalLink, ChevronLeft,
} from "lucide-react";
import api from "../lib/api";
import { Spinner, fmtMoney, fmtDate } from "../components/UI";
import { useAuth } from "../stores/auth";


// ── LiveClock ─────────────────────────────────────────────────────────────────
function LiveClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <span className="font-mono text-navy/70 text-base tabular-nums">
      {now.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
    </span>
  );
}

// ── BibleVerse ────────────────────────────────────────────────────────────────
function BibleVerse() {
  const [verse, setVerse] = useState<{ref: string; text: string} | null>(null);
  useEffect(() => {
    import("../lib/api").then(({ default: api }) =>
      api.get("/verse").then((r: any) => setVerse(r.data)).catch(() => {})
    );
  }, []);
  if (!verse) return null;
  return (
    /* versiculo-inline — texto no fundo branco, ao lado das horas */
    <span className="flex items-center gap-1.5 text-sm text-slate-500 italic min-w-0">
      <BookOpen size={13} className="text-bronze shrink-0" />
      <span className="truncate">"{verse.text}"
        <span className="not-italic text-xs text-slate-400 font-medium ml-1">— {verse.ref}</span>
      </span>
    </span>
  );
}

// ── NewsCarousel ──────────────────────────────────────────────────────────────
interface NewsItem { titulo: string; link: string; resumo: string; fonte: string; imagem?: string; data?: string; }

const NEWS_COLORS = ["from-navy to-navy/80", "from-bronze-deep to-bronze", "from-zinc-700 to-zinc-600",
                     "from-emerald-800 to-emerald-600", "from-indigo-800 to-indigo-600"];
const LOGO_INITIALS: Record<string, string> = { ConJur: "CJ", JOTA: "JT" };

function NewsCarousel() {
  const [itens, setItens] = useState<NewsItem[]>([]);
  const [idx, setIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [paused, setPaused] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    import("../lib/api").then(({ default: api }) =>
      api.get("/noticias?limit=15")
        .then((r: any) => setItens(r.data.itens || []))
        .catch(() => {})
        .finally(() => setLoading(false))
    );
  }, []);

  useEffect(() => {
    if (itens.length === 0 || paused) return;
    timer.current = setInterval(() => setIdx(i => (i + 1) % itens.length), 7000);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [itens.length, paused]);

  const prev = () => { setIdx(i => (i - 1 + itens.length) % itens.length); };
  const next = () => { setIdx(i => (i + 1) % itens.length); };

  if (loading) return (
    <div className="rounded-2xl bg-zinc-100 animate-pulse h-48 w-full" />
  );
  if (itens.length === 0) return null;

  const item = itens[idx];
  const color = NEWS_COLORS[idx % NEWS_COLORS.length];
  const initials = LOGO_INITIALS[item.fonte] || item.fonte.slice(0, 2).toUpperCase();

  return (
    <div className="rounded-2xl overflow-hidden shadow-md border border-zinc-100">
      {/* Título da seção */}
      <div className="bg-white px-5 py-3 flex items-center justify-between border-b border-zinc-100">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-bronze animate-pulse" />
          <span className="text-sm font-semibold text-navy">Notícias Jurídicas</span>
          <span className="text-xs text-zinc-400">• ConJur & JOTA</span>
        </div>
        <div className="flex items-center gap-1 text-xs text-zinc-400">
          <span>{idx + 1} / {itens.length}</span>
        </div>
      </div>

      {/* Card da notícia */}
      <div
        className={`relative bg-gradient-to-br ${color} min-h-[180px] flex flex-col justify-between p-6`}
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
      >
        {/* Imagem de fundo se disponível */}
        {item.imagem && (
          <div className="absolute inset-0 overflow-hidden">
            <img src={item.imagem} alt="" className="w-full h-full object-cover opacity-20" />
          </div>
        )}

        {/* Conteúdo */}
        <div className="relative z-10">
          <div className="flex items-center gap-2 mb-3">
            <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg
                             bg-white/20 text-white text-[11px] font-bold tracking-tight">
              {initials}
            </span>
            <span className="text-white/70 text-xs font-medium">{item.fonte}</span>
            {item.data && (
              <span className="text-white/50 text-xs ml-auto">
                {new Date(item.data).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}
              </span>
            )}
          </div>
          <h3 className="text-white font-semibold text-base leading-snug mb-2 line-clamp-2">
            {item.titulo}
          </h3>
          {item.resumo && (
            <p className="text-white/75 text-xs leading-relaxed line-clamp-3">{item.resumo}</p>
          )}
        </div>

        {/* Rodapé com link e navegação */}
        <div className="relative z-10 flex items-center justify-between mt-4">
          <a href={item.link} target="_blank" rel="noopener noreferrer"
             className="inline-flex items-center gap-1.5 text-xs font-semibold text-white/90
                        hover:text-white bg-white/10 hover:bg-white/20 rounded-lg px-3 py-1.5 transition">
            Ler matéria <ExternalLink size={11} />
          </a>
          <div className="flex items-center gap-1">
            <button onClick={prev}
              className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white transition"
              aria-label="Anterior">
              <ChevronLeft size={16} />
            </button>
            <button onClick={next}
              className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white transition"
              aria-label="Próxima">
              <ChevronRight size={16} />
            </button>
          </div>
        </div>

        {/* Indicadores (bolinhas) */}
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-1.5 z-10">
          {itens.slice(0, 12).map((_, i) => (
            <button key={i} onClick={() => setIdx(i)}
              className={`rounded-full transition-all ${
                i === idx ? "w-4 h-1.5 bg-white" : "w-1.5 h-1.5 bg-white/40 hover:bg-white/60"
              }`} aria-label={`Notícia ${i + 1}`} />
          ))}
        </div>
      </div>
    </div>
  );
}

// ── helpers ───────────────────────────────────────────────────────────────────
const ROLE_LEVEL: Record<string, number> = {
  superadmin: 9, admin: 8, socio: 7, advogado: 6,
  advogado_auxiliar: 5, financeiro: 4, estagiario: 3,
  secretaria: 2, cliente_externo: 1,
};
const isSocio = (role: string) => (ROLE_LEVEL[role] ?? 0) >= ROLE_LEVEL["socio"];

function verLink(to: string, txt = "Ver todos") {
  return (
    <Link to={to} className="text-xs font-semibold text-bronze hover:text-bronze-dark inline-flex items-center gap-1 shrink-0">
      {txt} <ArrowRight size={12} />
    </Link>
  );
}

// ── Donut SVG ─────────────────────────────────────────────────────────────────
function Donut({ segments, total }: { segments: { value: number; color: string; label: string }[]; total: number }) {
  const r = 56, sw = 14, c = 2 * Math.PI * r;
  let acc = 0;
  return (
    <div className="relative shrink-0" style={{ width: 140, height: 140 }}>
      <svg viewBox="0 0 140 140" width={140} height={140} style={{ transform: "rotate(-90deg)" }}>
        <circle cx="70" cy="70" r={r} fill="none" stroke="#F3EEE7" strokeWidth={sw} />
        {total > 0 && segments.map((s, i) => {
          const len = (s.value / total) * c;
          const off = -acc; acc += len;
          return <circle key={i} cx="70" cy="70" r={r} fill="none" stroke={s.color}
            strokeWidth={sw} strokeDasharray={`${len - 1} ${c - len + 1}`} strokeDashoffset={off} />;
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-serif text-3xl text-navy leading-none" style={{fontWeight: 400}}>{total}</span>
        <span className="text-[9px] uppercase tracking-[0.14em] text-slate-400 mt-1">casos</span>
      </div>
    </div>
  );
}

function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  return (
    <div className="flex-1 h-1.5 rounded-full bg-slate-100 overflow-hidden">
      <div className="h-full rounded-full" style={{ width: `${max > 0 ? (value / max) * 100 : 0}%`, background: color }} />
    </div>
  );
}

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="relative rounded-2xl border border-white/60 bg-gradient-to-br from-white to-slate-50/60 p-5 transition-all duration-300 hover:-translate-y-0.5"
      style={{ boxShadow: "0 10px 26px -14px rgba(15,31,61,0.25), 0 2px 6px -2px rgba(15,31,61,0.08), inset 0 1px 0 rgba(255,255,255,0.9)" }}>
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white to-transparent" />
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[13px] font-semibold uppercase tracking-wider text-slate-500">{title}</h3>
        {action}
      </div>
      {children}
    </div>
  );
}

// ── Bloco HOJE ────────────────────────────────────────────────────────────────
function BlocoHoje({ prazos, tarefas }: { prazos: any[]; tarefas: any[] }) {
  const hoje = new Date().toISOString().slice(0, 10);

  const prazosHoje = prazos.filter((p) => {
    const d = p.data_prazo?.slice(0, 10);
    return d === hoje || (p.dias_restantes != null && p.dias_restantes <= 0);
  });

  const tarefasHoje = tarefas.filter((t) => {
    const d = t.data_limite?.slice(0, 10) || t.prazo?.slice(0, 10);
    const naoFeita = (t.status ?? t.situacao) !== "concluida" && !t.concluida && !t.done;
    return naoFeita && (d === hoje || t.prioridade === "alta" || t.priority === "alta");
  }).slice(0, 5);

  const vencidos = prazos.filter((p) => (p.dias_restantes ?? 1) < 0);

  if (prazosHoje.length === 0 && tarefasHoje.length === 0 && vencidos.length === 0) {
    return (
      <div className="card p-4 border-l-4 border-emerald-400 flex items-center gap-3 bg-emerald-50/40">
        <CheckCircle2 size={20} className="text-emerald-500 shrink-0" />
        <div>
          <p className="font-semibold text-emerald-700 text-sm">Dia limpo — sem prazos ou urgências para hoje</p>
          <p className="text-xs text-emerald-600 mt-0.5">Continue acompanhando os casos em andamento</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bloco-3d relative rounded-2xl overflow-hidden border border-white/40"
      style={{ boxShadow: "0 16px 40px -16px rgba(15,31,61,0.40), 0 4px 10px -3px rgba(15,31,61,0.12), inset 0 1px 0 rgba(255,255,255,0.6)" }}>
      {/* Header do bloco */}
      <div className="bg-gradient-to-r from-navy to-navy/85 px-5 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <CalendarDays size={16} className="text-bronze" />
          <span className="font-serif font-semibold text-white">Hoje</span>
          <span className="text-xs text-navy-300 text-white/60 ml-1">
            {new Date().toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" })}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {vencidos.length > 0 && (
            <Link to="/prazos" className="flex items-center gap-1 text-xs font-bold text-red-300 hover:text-red-200">
              <AlertTriangle size={12} />{vencidos.length} vencido{vencidos.length > 1 ? "s" : ""}
            </Link>
          )}
          {prazosHoje.length > 0 && (
            <span className="text-xs text-white/70">{prazosHoje.length} prazo{prazosHoje.length > 1 ? "s" : ""} hoje</span>
          )}
          {tarefasHoje.length > 0 && (
            <span className="text-xs text-white/70">{tarefasHoje.length} tarefa{tarefasHoje.length > 1 ? "s" : ""} prioritária{tarefasHoje.length > 1 ? "s" : ""}</span>
          )}
        </div>
      </div>

      <div className="divide-y divide-bronze-50">
        {/* Prazos vencidos */}
        {vencidos.slice(0, 3).map((p, i) => (
          <Link key={`v-${i}`} to="/prazos"
            className="flex items-center gap-3 px-5 py-3 hover:bg-red-50/50 transition-colors">
            <span className="shrink-0 w-2 h-2 rounded-full bg-red-500" />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-red-700 truncate">{p.titulo}</p>
              {p.case_titulo && <p className="text-xs text-slate-400 truncate">{p.case_titulo}</p>}
            </div>
            <span className="shrink-0 text-xs font-bold text-red-600 bg-red-100 px-2 py-0.5 rounded-full">
              VENCIDO {Math.abs(p.dias_restantes ?? 0)}d
            </span>
          </Link>
        ))}

        {/* Prazos de hoje */}
        {prazosHoje.filter((p) => (p.dias_restantes ?? -1) >= 0).slice(0, 4).map((p, i) => (
          <Link key={`h-${i}`} to="/prazos"
            className="flex items-center gap-3 px-5 py-3 hover:bg-amber-50/50 transition-colors">
            <span className="shrink-0 w-2 h-2 rounded-full bg-amber-500" />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-slate-700 truncate">{p.titulo}</p>
              {p.case_titulo && <p className="text-xs text-slate-400 truncate">{p.case_titulo}</p>}
            </div>
            <span className="shrink-0 text-xs font-bold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">HOJE</span>
          </Link>
        ))}

        {/* Tarefas prioritárias */}
        {tarefasHoje.map((t, i) => (
          <Link key={`t-${i}`} to="/tarefas"
            className="flex items-center gap-3 px-5 py-3 hover:bg-bronze-50/50 transition-colors">
            <ListTodo size={14} className="shrink-0 text-bronze" />
            <p className="flex-1 text-sm text-slate-700 truncate">{t.titulo || t.descricao}</p>
            <ChevronRight size={14} className="text-slate-300 shrink-0" />
          </Link>
        ))}
      </div>
    </div>
  );
}

// ── KPI card (kpi-3d) ─────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, icon: Icon, to, alert = false, tone = "text-navy" }: any) {
  const cls = `kpi-3d group relative overflow-hidden rounded-2xl border p-5 transition-all duration-300 ease-out ${
    alert
      ? "border-red-200/60 bg-gradient-to-br from-red-50/70 to-white"
      : "border-white/60 bg-gradient-to-br from-white to-slate-50/80"
  }`;
  const shadow = alert
    ? "0 10px 30px -8px rgba(220,38,38,0.28), 0 2px 6px rgba(15,31,61,0.08), inset 0 1px 0 rgba(255,255,255,0.9)"
    : "0 12px 28px -12px rgba(15,31,61,0.30), 0 3px 8px -2px rgba(15,31,61,0.10), inset 0 1px 0 rgba(255,255,255,0.95)";
  const inner = (
    <>
      {/* brilho superior (gloss) */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white to-transparent" />
      <div className="pointer-events-none absolute -top-10 -right-8 w-28 h-28 rounded-full bg-white/40 blur-2xl opacity-60 group-hover:opacity-90 transition-opacity" />
      <div className="relative flex items-start justify-between">
        <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ring-1 transition-transform duration-300 group-hover:scale-105 ${
          alert ? "bg-gradient-to-br from-red-100 to-red-50 text-red-500 ring-red-200/50"
                : "bg-gradient-to-br from-bronze-50 to-amber-100/70 text-bronze-deep ring-bronze-pale/40"
        }`} style={{ boxShadow: "inset 0 1px 2px rgba(255,255,255,0.9), 0 4px 10px -3px rgba(15,31,61,0.25)" }}>
          <Icon size={19} />
        </div>
        {to && <ArrowRight size={15} className="text-slate-300 group-hover:text-bronze group-hover:translate-x-1 transition-all" />}
      </div>
      <div className="relative mt-4">
        <div className={`text-[34px] font-serif leading-none drop-shadow-sm ${alert ? "text-red-700" : tone}`} style={{fontWeight: 400}}>{value}</div>
        <div className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold mt-2">{label}</div>
        {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
      </div>
    </>
  );
  const style = { boxShadow: shadow } as React.CSSProperties;
  return to
    ? <Link to={to} className={cls} style={style}>{inner}</Link>
    : <div className={cls} style={style}>{inner}</div>;
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
function Tabs({ tabs, active, onChange }: { tabs: string[]; active: string; onChange: (t: string) => void }) {
  return (
    <div className="flex gap-1 p-1 rounded-xl w-fit bg-slate-100"
      style={{ boxShadow: "inset 0 2px 4px rgba(15,31,61,0.10)" }}>
      {tabs.map((t) => (
        <button key={t} onClick={() => onChange(t)}
          className={`px-4 py-1.5 text-sm font-medium rounded-lg transition-all ${active === t ? "bg-white text-navy" : "text-slate-500 hover:text-slate-700"}`}
          style={active === t ? { boxShadow: "0 2px 6px -1px rgba(15,31,61,0.20), inset 0 1px 0 rgba(255,255,255,0.9)" } : undefined}>
          {t}
        </button>
      ))}
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const { user } = useAuth();
  const role = (user as any)?.role ?? "";
  const ehSocio = isSocio(role);

  const [d, setD] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [prazos, setPrazos] = useState<any[]>([]);
  const [tarefas, setTarefas] = useState<any[]>([]);
  const [andamentos, setAndamentos] = useState<any[]>([]);
  const [rent, setRent] = useState<any>(null);
  const [juri, setJuri] = useState<any>(null);
  const [equipe, setEquipe] = useState<any[]>([]);
  const [tab, setTab] = useState("Carteira");

  useEffect(() => {
    const reqs: Promise<any>[] = [
      api.get("/dashboard/"),
      api.get("/analytics/case-health"),
      api.get("/deadlines/?status=pendente&page_size=100"),
      api.get("/tasks/"),
      api.get("/movimentos/recentes?limit=10"),
    ];
    if (ehSocio) {
      reqs.push(api.get("/analytics/rentabilidade"));
      reqs.push(api.get("/jurimetria/overview"));
      reqs.push(api.get("/atendimentos/dashboard"));
    }
    Promise.allSettled(reqs).then(([a, b, c, e, f, g, h, ii]) => {
      if (a.status === "fulfilled") setD(a.value.data);
      if (b.status === "fulfilled") setHealth(b.value.data);
      if (c.status === "fulfilled") setPrazos(c.value.data?.data ?? c.value.data?.items ?? []);
      if (e.status === "fulfilled") setTarefas(e.value.data?.data ?? e.value.data?.items ?? e.value.data ?? []);
      if (f.status === "fulfilled") setAndamentos(f.value.data ?? []);
      if (ehSocio) {
        if (g?.status === "fulfilled") setRent(g.value.data);
        if (h?.status === "fulfilled") setJuri(h.value.data);
        if (ii?.status === "fulfilled") setEquipe(ii.value.data ?? []);
      }
    });
  }, [ehSocio]);

  if (!d) return <div className="flex justify-center py-20"><Spinner /></div>;

  // Saúde
  const dist = health?.distribuicao ?? {};
  const healthSegs = [
    { label: "Saudável", value: dist.saudavel ?? 0, color: "#1D9E75" },
    { label: "Atenção",  value: dist.atencao  ?? 0, color: "#F59E0B" },
    { label: "Risco",    value: dist.risco    ?? 0, color: "#F97316" },
    { label: "Crítico",  value: dist.critico  ?? 0, color: "#EF4444" },
  ];
  const totalH = healthSegs.reduce((s, x) => s + x.value, 0);
  const areas = (d.casos?.por_area || []) as { area: string; total: number }[];
  const maxArea = Math.max(1, ...areas.map((a: any) => a.total));
  const barColors = ["#0f1f3d", "#26417a", "#AA8660", "#C4A07C", "#D8BE97", "#1D9E75"];
  const casosRisco = (health?.casos ?? []).filter((c: any) => !c.saudavel);

  // Financeiro (sócio)
  const cons = rent?.consolidado ?? {};
  const taxa = juri?.taxa_sucesso_geral;
  const maxAtend = Math.max(1, ...equipe.map((e) => e.total_atendimentos));

  // KPIs
  const kpis = [
    { label: "Casos ativos",     value: d.casos?.ativos ?? 0,         icon: Briefcase, to: "/casos" },
    { label: "A receber",        value: fmtMoney(d.financeiro?.pendente), icon: Wallet, to: "/honorarios" },
    { label: "Saúde média",      value: health?.score_medio ?? "—",   icon: Activity },
    { label: "Prazos vencidos",  value: d.prazos?.vencidos ?? 0,      icon: AlertTriangle, to: "/prazos",
      alert: (d.prazos?.vencidos ?? 0) > 0, tone: (d.prazos?.vencidos ?? 0) > 0 ? "text-red-700" : "text-navy" },
  ];

  return (
    <div className="space-y-5">
      {/* Cabeçalho mínimo */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <p className="eyebrow mb-0.5">EJC — Escritório</p>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="font-serif text-2xl text-navy" style={{fontWeight: 400}}>
              {new Date().toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" })}
            </h1>
            <LiveClock />
            <BibleVerse />
          </div>
        </div>
        {ehSocio && health?.score_medio && (
          <div className="text-right hidden sm:block">
            <p className="text-xs text-slate-400">Score médio carteira</p>
            <p className="font-serif text-3xl text-bronze-deep" style={{fontWeight: 400}}>{health.score_medio}</p>
          </div>
        )}
      </div>

      {/* ── HOJE ─────────────────────────────────────────────────── */}
      <BlocoHoje prazos={prazos} tarefas={tarefas} />

      {/* Alertas adicionais */}
      {d.pecas_aguardando_revisao > 0 && (
        <Link to="/pecas" className="flex items-center gap-2 text-sm font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
          <FileWarning size={15} className="shrink-0" />
          {d.pecas_aguardando_revisao} peça(s) IA aguardando revisão HITL
        </Link>
      )}

      {/* ── KPIs ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {kpis.map(({ label, value, icon, to, alert, tone }) => (
          <KpiCard key={label} label={label} value={String(value)} icon={icon} to={to} alert={alert} tone={tone} />
        ))}
      </div>

      {/* ── TABS: Carteira | Executivo (sócio) ───────────────────── */}
      {ehSocio && (
        <Tabs tabs={["Carteira", "Executivo"]} active={tab} onChange={setTab} />
      )}

      {/* ── TAB CARTEIRA ─────────────────────────────────────────── */}
      {tab === "Carteira" && (
        <>
          {/* Saúde + áreas */}
          <div className="grid lg:grid-cols-2 gap-5">
            <Section title="Saúde da carteira">
              {totalH === 0 ? (
                <p className="text-sm text-slate-400 py-8 text-center">Nenhum caso monitorado ainda</p>
              ) : (
                <div className="flex items-center gap-6">
                  <Donut segments={healthSegs} total={totalH} />
                  <div className="flex-1 space-y-3">
                    {healthSegs.map((s) => (
                      <div key={s.label}>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="flex items-center gap-2 text-slate-600">
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
              )}
            </Section>

            <Section title="Casos por área" action={verLink("/casos")}>
              {areas.length === 0 ? (
                <p className="text-sm text-slate-400 py-8 text-center">Nenhum caso ativo</p>
              ) : (
                <div className="space-y-3">
                  {areas.map((a: any, i: number) => (
                    <div key={a.area} className="flex items-center gap-3">
                      <span className="text-sm capitalize w-28 truncate text-slate-600">{a.area}</span>
                      <Bar value={a.total} max={maxArea} color={barColors[i % barColors.length]} />
                      <span className="text-sm font-bold text-navy w-5 text-right">{a.total}</span>
                    </div>
                  ))}
                </div>
              )}
            </Section>
          </div>

          {/* Prazos da semana + Tarefas */}
          <div className="grid lg:grid-cols-2 gap-5">
            <Section title="Próximos 7 dias" action={verLink("/prazos")}>
              {(() => {
                const semana = prazos.filter((p) => (p.dias_restantes ?? 99) <= 7 && (p.dias_restantes ?? -1) >= 0)
                  .sort((a, b) => (a.dias_restantes ?? 0) - (b.dias_restantes ?? 0)).slice(0, 7);
                if (semana.length === 0) return <p className="text-sm text-slate-400 py-6 text-center">Nenhum prazo nos próximos 7 dias</p>;
                return (
                  <div className="space-y-2.5">
                    {semana.map((p, i) => {
                      const n = p.dias_restantes ?? 0;
                      const chip = n === 0 ? { t: "Hoje", c: "bg-red-100 text-red-700" }
                        : n === 1 ? { t: "Amanhã", c: "bg-orange-100 text-orange-700" }
                        : { t: `${n}d`, c: "bg-amber-100 text-amber-700" };
                      return (
                        <div key={i} className="flex items-center justify-between gap-2 text-sm">
                          <span className="text-slate-700 truncate">{p.titulo}</span>
                          <span className={`shrink-0 text-[11px] font-semibold px-2 py-0.5 rounded-full ${chip.c}`}>{chip.t}</span>
                        </div>
                      );
                    })}
                  </div>
                );
              })()}
            </Section>

            <Section title="Pendências" action={verLink("/tarefas")}>
              {tarefas.filter((t) => (t.status ?? t.situacao) !== "concluida" && !t.concluida).length === 0 ? (
                <p className="text-sm text-slate-400 py-6 text-center">Nenhuma pendência aberta</p>
              ) : (
                <div className="space-y-2.5">
                  {tarefas.filter((t) => (t.status ?? t.situacao) !== "concluida" && !t.concluida).slice(0, 7).map((t, i) => (
                    <div key={i} className="flex items-center gap-2 text-sm">
                      <span className="w-1.5 h-1.5 rounded-full bg-bronze shrink-0" />
                      <span className="text-slate-700 truncate flex-1">{t.titulo || t.descricao}</span>
                      {t.prioridade === "alta" && <span className="text-[10px] font-bold text-red-500 shrink-0">ALTA</span>}
                    </div>
                  ))}
                </div>
              )}
            </Section>
          </div>

          {/* Andamentos + casos em risco */}
          <div className="grid lg:grid-cols-2 gap-5">
            <Section title="Andamentos recentes">
              {andamentos.length === 0 ? (
                <p className="text-sm text-slate-400 py-6 text-center">Sem movimentações recentes</p>
              ) : (
                <div className="space-y-1">
                  {andamentos.map((m: any) => {
                    const chips: Record<string, string> = {
                      peticao: "bg-sky-100 text-sky-700", decisao: "bg-purple-100 text-purple-700",
                      audiencia: "bg-amber-100 text-amber-700", intimacao: "bg-red-100 text-red-700",
                      ia: "bg-bronze-50 text-bronze-deep", nota: "bg-slate-100 text-slate-600",
                    };
                    return (
                      <Link key={m.id} to={`/casos/${m.case_id}`}
                        className="flex items-start gap-3 py-2.5 px-2 -mx-2 rounded-xl hover:bg-bronze-50/50 transition-colors">
                        <span className={`shrink-0 mt-0.5 text-[10px] font-bold px-2 py-0.5 rounded-full ${chips[m.tipo] ?? "bg-slate-100 text-slate-600"}`}>{m.tipo}</span>
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

            <Section title="Casos em atenção" action={verLink("/casos")}>
              {casosRisco.length === 0 ? (
                <div className="flex flex-col items-center py-6 text-slate-400">
                  <CheckCircle2 size={24} className="mb-2 text-emerald-400" />
                  <p className="text-sm text-emerald-600 font-medium">Carteira saudável</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {casosRisco.slice(0, 6).map((c: any) => {
                    const cls: Record<string, string> = {
                      critico: "bg-red-100 text-red-700", risco: "bg-orange-100 text-orange-700",
                      atencao: "bg-amber-100 text-amber-700",
                    };
                    return (
                      <Link key={c.case_id} to={`/casos/${c.case_id}`}
                        className="flex items-center justify-between gap-2 p-2.5 rounded-xl border border-bronze-50 hover:bg-bronze-50/40 transition-colors">
                        <p className="text-sm text-slate-700 truncate font-medium">
                          {c.numero_interno ? `[${c.numero_interno}] ` : ""}{c.titulo}
                        </p>
                        <span className={`shrink-0 text-[11px] font-bold px-2 py-0.5 rounded-full ${cls[c.classificacao] ?? cls.atencao}`}>
                          {c.classificacao} · {c.score}
                        </span>
                      </Link>
                    );
                  })}
                </div>
              )}
            </Section>
          </div>

          {/* Financeiro resumido (card único — o detalhe de prazos já está nos KPIs e em "Próximos 7 dias") */}
          <Section title="Financeiro do mês" action={verLink("/financeiro-dashboard")}>
            <div className="grid sm:grid-cols-3 gap-4 text-sm">
              {[
                { l: "Recebido no mês", v: fmtMoney(d.financeiro?.recebido_mes), c: "text-emerald-600" },
                { l: "Pendente",        v: fmtMoney(d.financeiro?.pendente),      c: "text-navy" },
                { l: "Em atraso",       v: fmtMoney(d.financeiro?.atrasado),      c: "text-red-600" },
              ].map(({ l, v, c }) => (
                <div key={l} className="rounded-xl bg-white/70 border border-slate-100 p-4"
                  style={{ boxShadow: "inset 0 1px 0 rgba(255,255,255,0.9), 0 4px 12px -6px rgba(15,31,61,0.15)" }}>
                  <div className="text-[11px] uppercase tracking-wide text-slate-400">{l}</div>
                  <div className={`text-xl font-serif font-bold mt-1 ${c}`}>{v}</div>
                </div>
              ))}
            </div>
          </Section>
        </>
      )}

      {/* ── TAB EXECUTIVO (sócios) ────────────────────────────────── */}
      {tab === "Executivo" && ehSocio && (
        <>
          {/* Financeiro detalhado + Jurimetria */}
          <div className="grid lg:grid-cols-5 gap-5">
            <div className="lg:col-span-3 card p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-serif font-semibold text-navy">Rentabilidade</h3>
                <span className={`text-xs font-bold px-2 py-1 rounded-full ${(cons.margem_pct ?? 0) >= 30 ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                  Margem {cons.margem_pct != null ? `${cons.margem_pct}%` : "—"}
                </span>
              </div>
              <div className="space-y-3">
                {[
                  { l: "Receita recebida", v: fmtMoney(cons.receita_recebida ?? d.financeiro?.recebido_mes ?? 0), c: "text-emerald-600" },
                  { l: "Custo (horas)",   v: fmtMoney(cons.custo_horas ?? 0),  c: "text-slate-700" },
                  { l: "Lucro estimado",  v: fmtMoney(cons.lucro ?? 0),        c: (cons.lucro ?? 0) >= 0 ? "text-emerald-600" : "text-red-500" },
                  { l: "Inadimplência",   v: fmtMoney(d.financeiro?.atrasado ?? 0), c: "text-red-500" },
                  { l: "Clientes ativos", v: String(d.clientes_ativos ?? 0),   c: "text-navy" },
                ].map(({ l, v, c }) => (
                  <div key={l} className="flex justify-between border-b border-bronze-50 pb-3 last:border-0">
                    <span className="text-sm text-slate-500">{l}</span>
                    <span className={`text-sm font-bold ${c}`}>{v}</span>
                  </div>
                ))}
              </div>
              {rent?.nota && <p className="text-xs text-slate-400 mt-3">{rent.nota}</p>}
            </div>

            <div className="lg:col-span-2 card p-5 flex flex-col">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-serif font-semibold text-navy">Jurimetria</h3>
                {verLink("/jurimetria")}
              </div>
              <div className="text-center mb-4">
                <p className="font-serif text-5xl font-bold text-bronze-deep">
                  {taxa != null ? `${Math.round(taxa * 100)}%` : "—"}
                </p>
                <p className="text-xs text-slate-400 mt-1">taxa de sucesso</p>
              </div>
              <div className="space-y-2 flex-1">
                {[
                  { l: "Vitórias", v: juri?.venceu ?? 0, c: "text-emerald-600" },
                  { l: "Derrotas", v: juri?.perdeu ?? 0, c: "text-red-500" },
                  { l: "Acordos",  v: juri?.acordo ?? 0, c: "text-amber-600" },
                ].map(({ l, v, c }) => (
                  <div key={l} className="flex justify-between text-sm">
                    <span className="text-slate-500">{l}</span>
                    <span className={`font-bold ${c}`}>{v}</span>
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-2 mt-4">
                {[
                  { l: "Tempo médio", v: juri?.tempo_medio_dias ? `${juri.tempo_medio_dias}d` : "—" },
                  { l: "Valor em causa", v: fmtMoney(juri?.valor_total_causa) },
                ].map(({ l, v }) => (
                  <div key={l} className="rounded-xl bg-bronze-50 p-3 text-center">
                    <p className="font-bold text-navy text-sm">{v}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">{l}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Performance da equipe */}
          <Section title="Performance da equipe" action={verLink("/atendimentos")}>
            {equipe.length === 0 ? (
              <p className="text-sm text-slate-400 py-6 text-center">Nenhum atendimento registrado</p>
            ) : (
              <div className="space-y-4">
                {equipe.slice(0, 8).map((e, i) => (
                  <div key={e.advogado_id ?? i} className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-navy/10 flex items-center justify-center shrink-0">
                      <span className="text-xs font-bold text-navy">{(e.nome ?? e.advogado_id ?? "?")[0].toUpperCase()}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium text-slate-700 truncate">
                          {e.nome ?? `Adv. ${e.advogado_id?.slice(0, 6)}`}
                        </span>
                        <div className="flex items-center gap-3 shrink-0 ml-2">
                          <span className="text-xs text-slate-400">{e.total_horas}h</span>
                          <span className="text-sm font-bold text-navy">{e.total_atendimentos} atend.</span>
                        </div>
                      </div>
                      <Bar value={e.total_atendimentos} max={maxAtend} color="#AA8660" />
                    </div>
                    {e.satisfacao_media > 0 && (
                      <span className="shrink-0 text-xs font-semibold text-bronze-deep">★ {e.satisfacao_media.toFixed(1)}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Section>
        </>
      )}
      {/* ── NOTÍCIAS JURÍDICAS ───────────────────────────────────── */}
      <NewsCarousel />
    </div>
  );
}
