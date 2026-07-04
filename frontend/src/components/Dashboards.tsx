// ── src/components/Dashboards.tsx ────────────────────────────────────────────
// Kit de dashboard reutilizável — design moderno branco+azul.
// Usado pelo Dashboard principal, pelos ramos do Direito e pela tela de Casos.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  BookOpen,
  Briefcase,
  Building2,
  CheckCircle2,
  Clock,
  FileText,
  FolderOpen,
  Layers,
  MessageCircle,
  Scale,
  ShieldCheck,
  Sparkles,
  Star,
  TrendingDown,
  TrendingUp,
  UserPlus,
  Users,
  Wallet,
} from "lucide-react";
import api from "../lib/api";
import { fmtMoney } from "./UI";

// Acentos por cor — ícone com fundo suave colorido
export const ACCENTS: Record<
  string,
  { bg: string; fg: string; bar: string; ring: string }
> = {
  blue: {
    bg: "bg-primary-50",
    fg: "text-primary-600",
    bar: "#C9A227",
    ring: "ring-primary-100",
  },
  bronze: {
    bg: "bg-warn-50",
    fg: "text-warn-600",
    bar: "#d97706",
    ring: "ring-warn-100",
  },
  emerald: {
    bg: "bg-success-50",
    fg: "text-success-600",
    bar: "#059669",
    ring: "ring-success-100",
  },
  amber: {
    bg: "bg-orange-50",
    fg: "text-orange-500",
    bar: "#f59e0b",
    ring: "ring-orange-100",
  },
  red: {
    bg: "bg-danger-50",
    fg: "text-danger-600",
    bar: "#dc2626",
    ring: "ring-danger-100",
  },
  purple: {
    bg: "bg-ai-50",
    fg: "text-ai-600",
    bar: "#9333ea",
    ring: "ring-ai-100",
  },
  sky: {
    bg: "bg-info-50",
    fg: "text-info-600",
    bar: "#0ea5e9",
    ring: "ring-info-100",
  },
  slate: {
    bg: "bg-slate-50",
    fg: "text-slate-500",
    bar: "#64748b",
    ring: "ring-slate-100",
  },
  indigo: {
    bg: "bg-primary-50",
    fg: "text-primary-600",
    bar: "#C9A227",
    ring: "ring-primary-100",
  },
};

export const RAMO_ACCENT: Record<string, string> = {
  amber: "amber",
  blue: "blue",
  red: "red",
  green: "emerald",
  slate: "slate",
  yellow: "amber",
  purple: "purple",
};

// ── KPI card ────────────────────────────────────────────────────────────────
export function Kpi({
  label,
  value,
  sub,
  delta,
  icon: Icon,
  accent = "blue",
  to,
}: {
  label: string;
  value: any;
  sub?: string;
  delta?: { v: string; up?: boolean };
  icon?: any;
  accent?: string;
  to?: string;
}) {
  const a = ACCENTS[accent] ?? ACCENTS.blue;
  const inner = (
    <div className="p-5">
      <div className="flex items-start justify-between gap-2 mb-3">
        {Icon && (
          <div
            className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ring-1 ${a.bg} ${a.ring}`}
          >
            <Icon size={17} className={a.fg} />
          </div>
        )}
        {delta && (
          <span
            className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full ${
              delta.up === false
                ? "bg-danger-50 text-danger-600"
                : "bg-success-50 text-success-600"
            }`}
          >
            {delta.up === false ? (
              <TrendingDown size={10} />
            ) : (
              <TrendingUp size={10} />
            )}
            {delta.v}
          </span>
        )}
        {!delta && to && (
          <ArrowUpRight
            size={15}
            className="text-gray-300 group-hover:text-primary-500 transition-colors shrink-0"
          />
        )}
      </div>
      <div className="text-[1.7rem] leading-none font-semibold text-gray-900 mb-1">
        {value}
      </div>
      <div className="text-[11px] font-medium text-gray-500 uppercase tracking-wide">
        {label}
      </div>
      {sub && <div className="text-xs text-gray-400 mt-1">{sub}</div>}
    </div>
  );

  const cls =
    "group card hover:-translate-y-0.5 transition-all duration-150 cursor-default";
  const linkCls =
    "group card hover:-translate-y-0.5 hover:border-primary-200 transition-all duration-150";
  return to ? (
    <Link to={to} className={linkCls}>
      {inner}
    </Link>
  ) : (
    <div className={cls}>{inner}</div>
  );
}

export function KpiGrid({
  children,
  cols = 4,
}: {
  children: any;
  cols?: 2 | 3 | 4;
}) {
  const g =
    cols === 2
      ? "lg:grid-cols-2"
      : cols === 3
        ? "lg:grid-cols-3"
        : "lg:grid-cols-4";
  return <div className={`grid grid-cols-2 ${g} gap-4`}>{children}</div>;
}

// ── Barras horizontais ───────────────────────────────────────────────────────
export function BarsH({
  data,
  accent = "blue",
}: {
  data: { label: string; value: number }[];
  accent?: string;
}) {
  const a = ACCENTS[accent] ?? ACCENTS.blue;
  const max = Math.max(1, ...data.map((d) => d.value));
  if (!data.length)
    return <p className="text-sm text-gray-400 py-6 text-center">Sem dados</p>;
  return (
    <div className="space-y-2.5">
      {data.map((d) => (
        <div key={d.label} className="flex items-center gap-3">
          <span className="text-xs text-gray-500 w-28 truncate capitalize">
            {d.label}
          </span>
          <div className="flex-1 h-2 rounded-full bg-gray-100 overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${(d.value / max) * 100}%`, background: a.bar }}
            />
          </div>
          <span className="text-xs font-semibold text-gray-700 w-7 text-right">
            {d.value}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Painel (card com título) ─────────────────────────────────────────────────
export function Panel({
  title,
  icon: Icon,
  action,
  children,
  className = "",
}: {
  title?: any;
  icon?: any;
  action?: any;
  children: any;
  className?: string;
}) {
  return (
    <div className={`card p-5 ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            {Icon && <Icon size={14} className="text-primary-500" />}
            {title}
          </h3>
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

// ── Dashboard de RAMO ─────────────────────────────────────────────────────────
const STATUS_LABEL: Record<string, string> = {
  ativo: "Ativos",
  em_andamento: "Em andamento",
  suspenso: "Suspensos",
  acordo: "Acordo",
  encerrado: "Encerrados",
  arquivado: "Arquivados",
};
const ENCERRADOS = new Set(["encerrado", "arquivado"]);

const AREA_LABEL: Record<string, string> = {
  civil: "Cível",
  trabalhista: "Trabalhista",
  consumidor: "Consumidor",
  familia: "Família",
  ambiental: "Ambiental",
  criminal: "Criminal",
  previdenciario: "Previdenciário",
  empresarial: "Empresarial",
  tributario: "Tributário",
};

export function RamoStats({
  casos,
  lista,
  cor = "blue",
  area,
}: {
  casos: any[];
  lista: any[] | null;
  cor?: string;
  area?: string;
}) {
  const accent = RAMO_ACCENT[cor] ?? "blue";
  const areaLabel = area ? (AREA_LABEL[area] ?? area) : "";
  const total = casos.length;
  const ativos = casos.filter((c) => !ENCERRADOS.has(String(c.status))).length;
  const valor = casos.reduce((s, c) => s + Number(c.valor_causa || 0), 0);
  const especializados = lista?.length ?? 0;

  const porStatus: Record<string, number> = {};
  casos.forEach((c) => {
    const s = String(c.status || "—");
    porStatus[s] = (porStatus[s] || 0) + 1;
  });
  const barras = Object.entries(porStatus)
    .map(([k, v]) => ({
      label: STATUS_LABEL[k] ?? k.replace(/_/g, " "),
      value: v,
    }))
    .sort((a, b) => b.value - a.value);

  if (total === 0 && especializados === 0) return null;

  return (
    <div className="mb-5">
      <KpiGrid>
        <Kpi
          label={areaLabel ? `Casos · ${areaLabel}` : "Casos da área"}
          value={total}
          icon={Briefcase}
          accent={accent}
          to="/casos"
          sub="Casos da área vinculada"
        />
        <Kpi
          label="Ativos"
          value={ativos}
          icon={FolderOpen}
          accent="emerald"
          sub={
            total ? `${Math.round((ativos / total) * 100)}% da área` : undefined
          }
        />
        <Kpi
          label="Registros especializados"
          value={especializados}
          icon={Scale}
          accent="purple"
          sub="Próprios deste ramo"
        />
        <Kpi
          label="Valor em causa"
          value={fmtMoney(valor)}
          icon={Wallet}
          accent="blue"
        />
      </KpiGrid>
      {barras.length > 0 && (
        <div className="mt-4">
          <Panel
            title={
              areaLabel
                ? `Casos (${areaLabel}) por situação`
                : "Casos por situação"
            }
          >
            <BarsH data={barras} accent={accent} />
          </Panel>
        </div>
      )}
    </div>
  );
}

// ── Dashboard de CASOS ────────────────────────────────────────────────────────
export function CasosStats() {
  const [d, setD] = useState<any>(null);
  useEffect(() => {
    api
      .get("/dashboard/")
      .then((r) => setD(r.data))
      .catch(() => {});
  }, []);
  if (!d) return null;

  const porArea = d?.casos?.por_area ?? [];
  const areas = porArea.map((a: any) => ({
    label: AREA_LABEL[a.area] ?? a.area,
    value: a.total,
  }));
  const somaArea = porArea.reduce((s: number, a: any) => s + (a.total || 0), 0);
  const total = d?.casos?.total || somaArea || "—";
  const novos = d?.casos?.novos_mes ?? d?.casos?.novos_30d;

  return (
    <div className="mb-5 space-y-4">
      <KpiGrid>
        <Kpi
          label="Total de casos"
          value={total}
          icon={Briefcase}
          accent="blue"
        />
        <Kpi
          label="Casos ativos"
          value={d?.casos?.ativos ?? "—"}
          icon={FolderOpen}
          accent="emerald"
          sub={novos != null ? `${novos} novos no mês` : undefined}
        />
        <Kpi
          label="Prazos vencidos"
          value={d?.prazos?.vencidos ?? 0}
          icon={Scale}
          accent={(d?.prazos?.vencidos ?? 0) > 0 ? "red" : "slate"}
          to="/atividades"
          sub={`${d?.prazos?.proximos_7d ?? 0} nos próx. 7 dias`}
        />
        <Kpi
          label="Clientes ativos"
          value={d?.clientes_ativos ?? "—"}
          icon={CheckCircle2}
          accent="indigo"
        />
      </KpiGrid>
      {areas.length > 0 && (
        <Panel title="Casos por área do Direito" icon={Scale}>
          <BarsH data={areas} accent="blue" />
        </Panel>
      )}
    </div>
  );
}

// ── Dashboard de CLIENTES / CRM ──────────────────────────────────────────────
export function ClientesStats() {
  const [d, setD] = useState<any>(null);
  useEffect(() => {
    api
      .get("/clients/", { params: { page_size: 200 } })
      .then((r) => setD(r.data))
      .catch(() => {});
  }, []);
  if (!d) return null;
  const lista: any[] = d.data || [];
  const total = d.total ?? lista.length;
  if (total === 0) return null;
  const ativos = lista.filter((c) => String(c.status) === "ativo").length;
  const leads = lista.filter((c) => String(c.status) === "lead").length;
  const pj = lista.filter((c) => String(c.tipo) === "PJ").length;
  const porArea: Record<string, number> = {};
  lista.forEach((c) => {
    const a = c.area_interesse || "—";
    porArea[a] = (porArea[a] || 0) + 1;
  });
  const barras = Object.entries(porArea)
    .map(([k, v]) => ({ label: k, value: v as number }))
    .filter((b) => b.label !== "—")
    .sort((a, b) => b.value - a.value)
    .slice(0, 8);
  return (
    <div className="mb-5 space-y-4">
      <KpiGrid>
        <Kpi
          label="Total de clientes"
          value={total}
          icon={Users}
          accent="blue"
        />
        <Kpi
          label="Ativos"
          value={ativos}
          icon={CheckCircle2}
          accent="emerald"
          sub={
            total ? `${Math.round((ativos / total) * 100)}% da base` : undefined
          }
        />
        <Kpi
          label="Leads"
          value={leads}
          icon={UserPlus}
          accent="amber"
          to="/crm-leads"
        />
        <Kpi
          label="Pessoa jurídica"
          value={pj}
          icon={Building2}
          accent="purple"
        />
      </KpiGrid>
      {barras.length > 0 && (
        <Panel title="Clientes por área de interesse" icon={Users}>
          <BarsH data={barras} accent="blue" />
        </Panel>
      )}
    </div>
  );
}

// ── Dashboard de DOCUMENTOS ──────────────────────────────────────────────────
export function DocumentosStats() {
  const [d, setD] = useState<any>(null);
  useEffect(() => {
    api
      .get("/documents/", { params: { page_size: 200 } })
      .then((r) => setD(r.data))
      .catch(() => {});
  }, []);
  if (!d) return null;
  const lista: any[] = d.data || [];
  const total = d.total ?? lista.length;
  if (total === 0) return null;
  const conf = lista.filter(
    (x) => x.confidencialidade && String(x.confidencialidade) !== "normal",
  ).length;
  const mesAtual = new Date().toISOString().slice(0, 7);
  const esteMes = lista.filter(
    (x) => String(x.created_at || "").slice(0, 7) === mesAtual,
  ).length;
  const porTipo: Record<string, number> = {};
  lista.forEach((x) => {
    const t = x.tipo || "outros";
    porTipo[t] = (porTipo[t] || 0) + 1;
  });
  const barras = Object.entries(porTipo)
    .map(([k, v]) => ({ label: k, value: v as number }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8);
  return (
    <div className="mb-5 space-y-4">
      <KpiGrid>
        <Kpi
          label="Total de documentos"
          value={total}
          icon={FolderOpen}
          accent="blue"
        />
        <Kpi
          label="Confidenciais"
          value={conf}
          icon={ShieldCheck}
          accent={conf > 0 ? "red" : "slate"}
        />
        <Kpi
          label="Este mês"
          value={esteMes}
          icon={FileText}
          accent="emerald"
        />
        <Kpi
          label="Tipos distintos"
          value={Object.keys(porTipo).length}
          icon={FolderOpen}
          accent="indigo"
        />
      </KpiGrid>
      {barras.length > 0 && (
        <Panel title="Documentos por tipo" icon={FileText}>
          <BarsH data={barras} accent="blue" />
        </Panel>
      )}
    </div>
  );
}

// ── Dashboard de CONHECIMENTO (base RAG) ─────────────────────────────────────
export function ConhecimentoStats() {
  const [d, setD] = useState<any>(null);
  useEffect(() => {
    api
      .get("/rag/stats")
      .then((r) => setD(r.data))
      .catch(() => {});
  }, []);
  if (!d) return null;
  const cats = (d.por_categoria || [])
    .map((c: any) => ({
      label: String(c.categoria).replace(/_/g, " "),
      value: c.total,
    }))
    .slice(0, 8);
  const pct = d.total_chunks
    ? Math.round((d.chunks_indexados / d.total_chunks) * 100)
    : 0;
  if (!d.total_docs) return null;
  return (
    <div className="mb-5 space-y-4">
      <KpiGrid>
        <Kpi
          label="Documentos na base"
          value={Number(d.total_docs).toLocaleString("pt-BR")}
          icon={BookOpen}
          accent="blue"
        />
        <Kpi
          label="Trechos (chunks)"
          value={Number(d.total_chunks).toLocaleString("pt-BR")}
          icon={Layers}
          accent="indigo"
        />
        <Kpi
          label="Indexados (vetor)"
          value={`${pct}%`}
          icon={Sparkles}
          accent="emerald"
          sub={`${Number(d.chunks_indexados).toLocaleString("pt-BR")} chunks`}
        />
        <Kpi
          label="Categorias"
          value={(d.por_categoria || []).length}
          icon={Scale}
          accent="purple"
        />
      </KpiGrid>
      {cats.length > 0 && (
        <Panel title="Conhecimento por categoria" icon={BookOpen}>
          <BarsH data={cats} accent="blue" />
        </Panel>
      )}
    </div>
  );
}

// ── Dashboard de ATENDIMENTO ─────────────────────────────────────────────────
export function AtendimentoStats() {
  const [d, setD] = useState<any>(null);
  useEffect(() => {
    const ano = new Date().getFullYear();
    api
      .get(`/atendimentos/stats?ano=${ano}`)
      .then((r) => setD(r.data))
      .catch(() => {});
  }, []);
  if (!Array.isArray(d)) return null;
  const totalAno = d.reduce((s: number, m: any) => s + (m.total || 0), 0);
  if (totalAno === 0) return null;
  const horas = d.reduce((s: number, m: any) => s + (m.total_horas || 0), 0);
  const sats = d.filter((m: any) => m.satisfacao_media > 0);
  const satMedia = sats.length
    ? sats.reduce((s: number, m: any) => s + m.satisfacao_media, 0) /
      sats.length
    : 0;
  const barras = d
    .filter((m: any) => m.total > 0)
    .map((m: any) => ({ label: m.mes_nome, value: m.total }));
  return (
    <div className="mb-5 space-y-4">
      <KpiGrid cols={3}>
        <Kpi
          label="Atendimentos no ano"
          value={totalAno}
          icon={MessageCircle}
          accent="blue"
        />
        <Kpi
          label="Horas atendidas"
          value={horas.toFixed(1)}
          icon={Clock}
          accent="indigo"
        />
        <Kpi
          label="Satisfação média"
          value={satMedia ? `${satMedia.toFixed(1)}/5` : "—"}
          icon={Star}
          accent="amber"
        />
      </KpiGrid>
      {barras.length > 0 && (
        <Panel title="Atendimentos por mês" icon={MessageCircle}>
          <BarsH data={barras} accent="blue" />
        </Panel>
      )}
    </div>
  );
}
