// Central Eletrônica de Diagnóstico — painel de operação (sócio+).
// Consome GET /diagnostico/central e apresenta o estado de saúde do sistema:
// semáforo geral, contagens do resumo e um card por subsistema com seus extras.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  Bot,
  CalendarClock,
  CheckCircle2,
  CircleOff,
  Database,
  GitBranch,
  HardDrive,
  Lock,
  PlugZap,
  RefreshCw,
  Search,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import api from "../lib/api";
import { Badge, Empty, PageHeader, Spinner } from "../components/UI";
import { detalheErro, statusErro } from "../utils/erro";

// ── Contrato (GET /diagnostico/central) ───────────────────────────────────────
type Status = "ok" | "alerta" | "erro" | "desligado";

type IntegracaoItem = {
  chave: string;
  label: string;
  grupo: string;
  status: Status;
  detalhe: string;
  acao_sugerida: string;
};

type SchedulerJob = { id: string; proxima_execucao: string | null };

type SchedulerFonte = {
  slug: string;
  ultima_execucao: string | null;
  ultimo_status: string | null;
  registros_novos: number | null;
};

type Subsistema = {
  nome: string;
  status: Status;
  detalhe: string;
  acao_sugerida: string;
  latencia_ms: number | null;
  // extras opcionais por subsistema
  pgvector?: boolean;
  conexoes_ativas?: number | null;
  heads_esperadas?: string[];
  revisoes_aplicadas?: string[];
  provedores?: string[];
  itens?: IntegracaoItem[];
  resumo?: { total: number; ok: number; alerta: number; desligado: number };
  provider?: string;
  busca?: string;
  rodando?: boolean;
  jobs?: SchedulerJob[];
  fontes?: SchedulerFonte[];
  fontes_com_erro?: string[];
  caminho?: string;
  livre_gb?: number;
  total_gb?: number;
  percentual_livre?: number;
  coletor?: string | null;
};

type DiagnosticoPayload = {
  gerado_em: string;
  status_geral: Status;
  resumo: { ok: number; alerta: number; erro: number; desligado: number };
  subsistemas: Subsistema[];
  aviso: string;
};

// ── Metadados de status ───────────────────────────────────────────────────────
const STATUS_META: Record<
  Status,
  {
    label: string;
    tone: "green" | "amber" | "red" | "slate";
    icon: LucideIcon;
    dot: string;
    ring: string;
    text: string;
  }
> = {
  ok: {
    label: "Operacional",
    tone: "green",
    icon: CheckCircle2,
    dot: "bg-success-500",
    ring: "ring-success-200",
    text: "text-success-700",
  },
  alerta: {
    label: "Atenção",
    tone: "amber",
    icon: AlertTriangle,
    dot: "bg-warn-500",
    ring: "ring-warn-200",
    text: "text-warn-700",
  },
  erro: {
    label: "Erro",
    tone: "red",
    icon: XCircle,
    dot: "bg-danger-500",
    ring: "ring-danger-200",
    text: "text-danger-700",
  },
  desligado: {
    label: "Desligado",
    tone: "slate",
    icon: CircleOff,
    dot: "bg-slate-400",
    ring: "ring-slate-200",
    text: "text-slate-500",
  },
};

const GERAL_META: Record<Status, { titulo: string; descricao: string }> = {
  ok: {
    titulo: "Todos os sistemas operacionais",
    descricao: "Nenhum subsistema exige ação no momento.",
  },
  alerta: {
    titulo: "Atenção necessária",
    descricao: "Um ou mais subsistemas pedem verificação.",
  },
  erro: {
    titulo: "Falha detectada",
    descricao: "Há subsistema em erro — aja o quanto antes.",
  },
  desligado: {
    titulo: "Diagnóstico inativo",
    descricao: "Nenhum subsistema ativo respondeu.",
  },
};

// Ícone do subsistema por palavra-chave no nome (resiliente a rótulos futuros).
function iconePara(nome: string): LucideIcon {
  const n = nome.toLowerCase();
  if (n.includes("banco")) return Database;
  if (n.includes("migration")) return GitBranch;
  if (n.includes("ia") || n.includes("provedor")) return Bot;
  if (n.includes("integra")) return PlugZap;
  if (n.includes("rag") || n.includes("embedding") || n.includes("busca"))
    return Search;
  if (n.includes("scheduler") || n.includes("job")) return CalendarClock;
  if (n.includes("disco") || n.includes("upload")) return HardDrive;
  if (n.includes("erro")) return AlertOctagon;
  return Activity;
}

function fmtDataHora(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("pt-BR");
}

// ── Página ────────────────────────────────────────────────────────────────────
export default function CentralDiagnostico() {
  const [data, setData] = useState<DiagnosticoPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<{
    tipo: "acesso" | "geral";
    msg: string;
  } | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const timerRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get<DiagnosticoPayload>("/diagnostico/central");
      setData(res.data);
      setErro(null);
    } catch (e: unknown) {
      const status = statusErro(e);
      if (status === 403) {
        setErro({
          tipo: "acesso",
          msg: "Acesso restrito a sócios e administradores.",
        });
      } else {
        setErro({
          tipo: "geral",
          msg: detalheErro(e, "Não foi possível carregar o diagnóstico."),
        });
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Auto-refresh opcional a cada 60s.
  useEffect(() => {
    if (!autoRefresh) return;
    timerRef.current = window.setInterval(() => void load(), 60_000);
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, [autoRefresh, load]);

  const geralMeta = data
    ? STATUS_META[data.status_geral]
    : STATUS_META.desligado;
  const geralTexto = data
    ? GERAL_META[data.status_geral]
    : GERAL_META.desligado;

  const contagens = useMemo(
    () =>
      [
        ["ok", "Operacional", data?.resumo.ok],
        ["alerta", "Atenção", data?.resumo.alerta],
        ["erro", "Erro", data?.resumo.erro],
        ["desligado", "Desligado", data?.resumo.desligado],
      ] as [Status, string, number | undefined][],
    [data?.resumo],
  );

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        eyebrow="Operação"
        title="Central de Diagnóstico"
        subtitle="Saúde dos subsistemas do EJC em tempo real. Somente leitura — não revela segredos."
        actions={
          <>
            <label className="flex cursor-pointer select-none items-center gap-2 text-xs text-slate-500">
              <input
                type="checkbox"
                className="h-4 w-4 accent-ouro"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              Auto (60s)
            </label>
            <button
              type="button"
              className="btn-primary"
              disabled={loading}
              onClick={() => void load()}
            >
              <RefreshCw
                className={`h-4 w-4 ${loading ? "animate-spin" : ""}`}
              />
              Verificar agora
            </button>
          </>
        }
      />

      {erro?.tipo === "acesso" ? (
        <Empty
          icon={Lock}
          titulo="Acesso restrito"
          descricao="A Central de Diagnóstico está disponível apenas para sócios e administradores."
        />
      ) : erro?.tipo === "geral" && !data ? (
        <Empty
          icon={AlertOctagon}
          titulo="Não foi possível carregar o diagnóstico"
          descricao={erro.msg}
          acao={
            <button
              type="button"
              className="btn-secondary"
              onClick={() => void load()}
            >
              <RefreshCw className="h-4 w-4" />
              Tentar novamente
            </button>
          }
        />
      ) : loading && !data ? (
        <Spinner />
      ) : data ? (
        <div className="space-y-6">
          {/* Semáforo geral + contagens do resumo */}
          <section className="card p-6">
            <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
              <div className="flex items-center gap-4">
                <span
                  className={`grid h-16 w-16 shrink-0 place-items-center rounded-full ring-4 ${geralMeta.ring} ${geralMeta.dot}`}
                >
                  <geralMeta.icon className="h-8 w-8 text-white" />
                </span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h2 className="font-serif text-xl font-semibold text-slate-950">
                      {geralTexto.titulo}
                    </h2>
                    <Badge tone={geralMeta.tone}>{geralMeta.label}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-slate-500">
                    {geralTexto.descricao}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">
                    Gerado em {fmtDataHora(data.gerado_em)}
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 md:w-auto">
                {contagens.map(([key, label, valor]) => {
                  const meta = STATUS_META[key];
                  return (
                    <div key={key} className="card px-4 py-3 text-center">
                      <div
                        className={`text-2xl font-semibold tabular-nums ${meta.text}`}
                      >
                        {valor ?? 0}
                      </div>
                      <div className="mt-0.5 text-[11px] text-slate-400">
                        {label}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {data.aviso && (
              <p className="mt-5 border-t border-slate-100 pt-4 text-xs text-slate-400">
                {data.aviso}
              </p>
            )}
          </section>

          {/* Cards por subsistema */}
          <div className="grid gap-4 lg:grid-cols-2">
            {data.subsistemas.map((sub) => (
              <SubsistemaCard key={sub.nome} sub={sub} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ── Card de subsistema ──────────────────────────────────────────────────────────
function SubsistemaCard({ sub }: { sub: Subsistema }) {
  const meta = STATUS_META[sub.status] ?? STATUS_META.desligado;
  const Icone = iconePara(sub.nome);

  return (
    <section className="card flex flex-col gap-3 p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span
            className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ring-1 ${meta.ring} ${meta.text}`}
          >
            <Icone className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-slate-800">
              {sub.nome}
            </h3>
            {sub.latencia_ms != null && (
              <span className="text-[11px] text-slate-400">
                {sub.latencia_ms} ms
              </span>
            )}
          </div>
        </div>
        <Badge tone={meta.tone}>{meta.label}</Badge>
      </div>

      <p className="text-sm leading-5 text-slate-600">{sub.detalhe}</p>

      {sub.status !== "ok" && sub.acao_sugerida && (
        <div
          className={`rounded-xl px-3 py-2 text-xs leading-5 ring-1 ring-inset ${meta.ring} ${meta.text}`}
        >
          <span className="font-semibold">Ação sugerida: </span>
          {sub.acao_sugerida}
        </div>
      )}

      <SubsistemaExtras sub={sub} />
    </section>
  );
}

// Renderiza os extras relevantes conforme as chaves presentes no subsistema.
function SubsistemaExtras({ sub }: { sub: Subsistema }) {
  const blocos: React.ReactNode[] = [];

  // Banco de dados
  if (sub.pgvector != null || sub.conexoes_ativas != null) {
    blocos.push(
      <div key="banco" className="flex flex-wrap gap-2">
        {sub.pgvector != null && (
          <Chip
            tone={sub.pgvector ? "green" : "amber"}
            label={sub.pgvector ? "pgvector instalado" : "pgvector ausente"}
          />
        )}
        {sub.conexoes_ativas != null && (
          <Chip tone="slate" label={`${sub.conexoes_ativas} conexões ativas`} />
        )}
      </div>,
    );
  }

  // Migrations
  if (sub.heads_esperadas?.length || sub.revisoes_aplicadas?.length) {
    blocos.push(
      <dl key="migrations" className="grid grid-cols-1 gap-1 text-xs">
        <LinhaExtra
          termo="Head esperada"
          valor={(sub.heads_esperadas ?? []).join(", ") || "—"}
        />
        <LinhaExtra
          termo="Revisão aplicada"
          valor={(sub.revisoes_aplicadas ?? []).join(", ") || "—"}
        />
      </dl>,
    );
  }

  // IA / Provedores
  if (sub.provedores) {
    blocos.push(
      <div key="ia" className="flex flex-wrap gap-2">
        {sub.provedores.length ? (
          sub.provedores.map((p) => <Chip key={p} tone="blue" label={p} />)
        ) : (
          <Chip tone="slate" label="nenhum provedor configurado" />
        )}
      </div>,
    );
  }

  // RAG
  if (sub.provider || sub.busca) {
    blocos.push(
      <div key="rag" className="flex flex-wrap gap-2">
        {sub.provider && (
          <Chip tone="slate" label={`provider: ${sub.provider}`} />
        )}
        {sub.busca && (
          <Chip
            tone={sub.busca === "semantica" ? "green" : "amber"}
            label={`busca: ${sub.busca}`}
          />
        )}
      </div>,
    );
  }

  // Disco — barra de % livre
  if (sub.percentual_livre != null) {
    const pct = sub.percentual_livre;
    const barra =
      pct < 10 ? "bg-danger-500" : pct < 25 ? "bg-warn-500" : "bg-success-500";
    blocos.push(
      <div key="disco" className="space-y-1">
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>{sub.caminho}</span>
          <span className="tabular-nums">
            {sub.livre_gb} / {sub.total_gb} GB livres
          </span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className={`h-full rounded-full ${barra}`}
            style={{ width: `${Math.min(Math.max(pct, 0), 100)}%` }}
          />
        </div>
        <div className="text-right text-[11px] text-slate-400">
          {pct}% livre
        </div>
      </div>,
    );
  }

  // Integrações — lista de itens com status
  if (sub.itens?.length) {
    blocos.push(
      <ul key="integracoes" className="space-y-1">
        {sub.itens.map((it) => {
          const m = STATUS_META[it.status] ?? STATUS_META.desligado;
          return (
            <li
              key={it.chave}
              className="flex items-center justify-between gap-2 text-xs"
            >
              <span className="flex min-w-0 items-center gap-2">
                <span className={`h-2 w-2 shrink-0 rounded-full ${m.dot}`} />
                <span className="truncate text-slate-600">{it.label}</span>
              </span>
              <span className={`shrink-0 ${m.text}`}>{m.label}</span>
            </li>
          );
        })}
      </ul>,
    );
  }

  // Scheduler — jobs + fontes com erro
  if (sub.rodando != null || sub.jobs || sub.fontes_com_erro?.length) {
    blocos.push(
      <div key="scheduler" className="space-y-2 text-xs">
        <div className="flex flex-wrap gap-2">
          <Chip
            tone={sub.rodando ? "green" : "amber"}
            label={sub.rodando ? "scheduler ativo" : "scheduler parado"}
          />
          {sub.jobs && <Chip tone="slate" label={`${sub.jobs.length} jobs`} />}
        </div>
        {sub.jobs?.length ? (
          <ul className="space-y-1">
            {sub.jobs.map((job) => (
              <li
                key={job.id}
                className="flex items-center justify-between gap-2 text-slate-500"
              >
                <span className="truncate">{job.id}</span>
                <span className="shrink-0 tabular-nums text-slate-400">
                  {fmtDataHora(job.proxima_execucao)}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        {sub.fontes_com_erro?.length ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-danger-700">Fontes com erro:</span>
            {sub.fontes_com_erro.map((f) => (
              <Chip key={f} tone="red" label={f} />
            ))}
          </div>
        ) : null}
      </div>,
    );
  }

  // Erros recentes — coletor
  if ("coletor" in sub) {
    blocos.push(
      <div key="erros" className="flex flex-wrap gap-2">
        <Chip
          tone={sub.coletor ? "green" : "slate"}
          label={
            sub.coletor ? `coletor: ${sub.coletor}` : "sem coletor externo"
          }
        />
      </div>,
    );
  }

  if (!blocos.length) return null;
  return (
    <div className="space-y-2 border-t border-slate-100 pt-3">{blocos}</div>
  );
}

function LinhaExtra({ termo, valor }: { termo: string; valor: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-slate-400">{termo}</dt>
      <dd className="truncate font-mono text-[11px] text-slate-600">{valor}</dd>
    </div>
  );
}

function Chip({
  label,
  tone,
}: {
  label: string;
  tone: "green" | "amber" | "red" | "slate" | "blue";
}) {
  const map: Record<typeof tone, string> = {
    green: "bg-success-50 text-success-700 ring-success-200",
    amber: "bg-warn-50 text-warn-700 ring-warn-200",
    red: "bg-danger-50 text-danger-700 ring-danger-200",
    slate: "bg-slate-100 text-slate-600 ring-slate-200",
    blue: "bg-primary-50 text-primary-700 ring-primary-200",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${map[tone]}`}
    >
      {label}
    </span>
  );
}
