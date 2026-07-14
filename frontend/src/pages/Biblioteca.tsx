import { useEffect, useState, useCallback } from "react";
import {
  Search,
  Plus,
  Star,
  TrendingUp,
  Scale,
  BookOpen,
  Gavel,
  ScrollText,
  Tag,
  CheckCircle,
  X,
  Sparkles,
  Target,
} from "lucide-react";
import api from "../lib/api";
import { PageHeader, Spinner, fmtDate } from "../components/UI";

// ─── Tipos ────────────────────────────────────────────────────────────────────
interface Tese {
  id: string;
  titulo: string;
  descricao: string;
  fundamentacao: string;
  jurisprudencia: string;
  area_juridica: string;
  tribunal: string;
  tipo: string;
  status: string;
  taxa_sucesso: number;
  vezes_usada: number;
  vezes_venceu: number;
  tags: string;
  created_at: string;
  relevancia?: number;
}

interface Memoria {
  id: string;
  titulo: string;
  conteudo: string;
  tipo: string;
  resultado: string;
  area_direito: string;
  tags: string[];
  created_at: string;
  case_id: string;
}

const AREA_LABELS: Record<string, string> = {
  civel: "Cível",
  trabalhista: "Trabalhista",
  penal: "Penal",
  empresarial: "Empresarial",
  administrativo: "Administrativo",
  bancario: "Bancário",
  tributario: "Tributário",
  ambiental: "Ambiental",
};

const TIPO_ICON: Record<string, React.ElementType> = {
  escritorio: Scale,
  sugerida_ia: Sparkles,
  doutrina: BookOpen,
  jurisprudencia: Gavel,
  externa: ScrollText,
};

const RESULTADO_CLASS: Record<string, string> = {
  favoravel: "badge-success",
  desfavoravel: "badge-danger",
  parcial: "badge-warn",
  acordo: "badge-info",
  em_andamento: "badge-neutral",
};

const RESULTADO_LABEL: Record<string, string> = {
  favoravel: "Favorável",
  desfavoravel: "Desfavorável",
  parcial: "Parcial",
  acordo: "Acordo",
  em_andamento: "Em andamento",
};

// ─── Componentes ──────────────────────────────────────────────────────────────
function TaxaSucesso({ v }: { v: number }) {
  const cor =
    v >= 70 ? "text-success-600" : v >= 40 ? "text-warn-600" : "text-slate-400";
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 bg-slate-100 rounded-full h-1.5">
        <div
          className={`h-1.5 rounded-full ${v >= 70 ? "bg-success-400" : v >= 40 ? "bg-warn-400" : "bg-slate-300"}`}
          style={{ width: `${Math.min(v, 100)}%` }}
        />
      </div>
      <span className={`text-xs ${cor}`}>
        {v > 0 ? `${v.toFixed(0)}%` : "—"}
      </span>
    </div>
  );
}

function CardTese({ t, onClick }: { t: Tese; onClick: () => void }) {
  const Icon = TIPO_ICON[t.tipo] ?? Scale;
  const tags = t.tags
    ? t.tags
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
    : [];
  return (
    <div
      onClick={onClick}
      className="card p-4 cursor-pointer hover:shadow-card-hover transition-all hover:border-bronze/30 group"
    >
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-lg bg-bronze-50 text-bronze flex-shrink-0 mt-0.5">
          <Icon className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-serif text-base text-navy-800 leading-snug group-hover:text-bronze-deep transition-colors">
              {t.titulo}
            </h3>
            {t.vezes_usada > 0 && (
              <span className="badge badge-neutral text-[10px] flex-shrink-0">
                <Star className="w-2.5 h-2.5" /> {t.vezes_usada}×
              </span>
            )}
          </div>
          {t.descricao && (
            <p className="text-sm text-slate-500 mt-1 line-clamp-2">
              {t.descricao}
            </p>
          )}
          <div className="flex items-center flex-wrap gap-2 mt-2.5">
            {t.area_juridica && (
              <span className="badge badge-info text-[10px]">
                {AREA_LABELS[t.area_juridica] ?? t.area_juridica}
              </span>
            )}
            {t.tribunal && (
              <span className="badge badge-neutral text-[10px]">
                {t.tribunal}
              </span>
            )}
            {t.taxa_sucesso > 0 && <TaxaSucesso v={t.taxa_sucesso} />}
            {t.relevancia !== undefined && (
              <span className="badge badge-warn text-[10px]">
                <Target className="w-2.5 h-2.5" />{" "}
                {(t.relevancia * 100).toFixed(0)}% relevância
              </span>
            )}
          </div>
          {tags.length > 0 && (
            <div className="flex gap-1 mt-2 flex-wrap">
              {tags.slice(0, 4).map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center gap-0.5 text-[10px] text-bronze-deep bg-bronze-50 px-1.5 py-0.5 rounded"
                >
                  <Tag className="w-2 h-2" /> {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CardMemoria({ m }: { m: Memoria }) {
  return (
    <div className="card p-4">

      <div className="flex items-start gap-3">
        <div className="p-2 rounded-lg bg-navy-50 text-navy-600 flex-shrink-0 mt-0.5">
          <CheckCircle className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-serif text-base text-navy-800 leading-snug">
              {m.titulo}
            </h3>
            {m.resultado && (
              <span
                className={`badge ${RESULTADO_CLASS[m.resultado] ?? "badge-neutral"} text-[10px] flex-shrink-0`}
              >
                {RESULTADO_LABEL[m.resultado] ?? m.resultado}
              </span>
            )}
          </div>
          <p className="text-sm text-slate-500 mt-1 line-clamp-2">
            {m.conteudo}
          </p>
          <div className="flex items-center gap-2 mt-2.5 flex-wrap">
            {m.area_direito && (
              <span className="badge badge-neutral text-[10px]">
                {AREA_LABELS[m.area_direito] ?? m.area_direito}
              </span>
            )}
            <span className="text-[11px] text-slate-400">
              {fmtDate(m.created_at)}
            </span>
            {m.tags?.slice(0, 3).map((t) => (
              <span
                key={t}
                className="inline-flex items-center gap-0.5 text-[10px] text-bronze-deep bg-bronze-50 px-1.5 py-0.5 rounded"
              >
                <Tag className="w-2 h-2" /> {t}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function ModalTese({ tese, onClose }: { tese: Tese; onClose: () => void }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-float max-w-2xl w-full max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6 border-b border-bronze-pale sticky top-0 bg-white rounded-t-2xl flex items-start justify-between gap-4">
          <div>
            <p className="eyebrow mb-1">Tese jurídica</p>
            <h2 className="font-serif text-xl text-navy-800">{tese.titulo}</h2>
          </div>
          <button onClick={onClose} className="btn-ghost p-2 flex-shrink-0">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-6 space-y-4">
          {tese.descricao && (
            <div>
              <p className="label-caps mb-1.5">Descrição</p>
              <p className="text-sm text-slate-600 leading-relaxed">
                {tese.descricao}
              </p>
            </div>
          )}
          {tese.fundamentacao && (
            <div>
              <p className="label-caps mb-1.5">Fundamentação</p>
              <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-wrap">
                {tese.fundamentacao}
              </p>
            </div>
          )}
          {tese.jurisprudencia && (
            <div>
              <p className="label-caps mb-1.5">Jurisprudência</p>
              <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-wrap">
                {tese.jurisprudencia}
              </p>
            </div>
          )}
          <div className="flex flex-wrap gap-3 pt-2 border-t border-bronze-pale">
            {tese.vezes_usada > 0 && (
              <div className="text-center">
                <p className="text-lg font-serif text-navy-700">
                  {tese.vezes_usada}
                </p>
                <p className="label-caps">usos</p>
              </div>
            )}
            {tese.vezes_venceu > 0 && (
              <div className="text-center">
                <p className="text-lg font-serif text-success-600">
                  {tese.vezes_venceu}
                </p>
                <p className="label-caps">vitórias</p>
              </div>
            )}
            {tese.taxa_sucesso > 0 && (
              <div className="text-center">
                <p className="text-lg font-serif text-bronze-deep">
                  {tese.taxa_sucesso.toFixed(0)}%
                </p>
                <p className="label-caps">sucesso</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Página principal ──────────────────────────────────────────────────────────
export default function Biblioteca() {
  const [aba, setAba] = useState<"teses" | "estrategias">("teses");
  const [busca, setBusca] = useState("");
  const [buscaInput, setBuscaInput] = useState("");
  const [area, setArea] = useState("");
  const [teses, setTeses] = useState<Tese[]>([]);
  const [memorias, setMemorias] = useState<Memoria[]>([]);
  const [loading, setLoading] = useState(false);
  const [teseSelecionada, setTeseSelecionada] = useState<Tese | null>(null);
  const [stats, setStats] = useState({
    teses: 0,
    estrategias: 0,
    sucesso_medio: 0,
  });

  const carregarTeses = useCallback(async () => {
    setLoading(true);
    try {
      if (busca.trim().length >= 3) {
        const { data } = await api.get("/teses/busca-avancada", {
          params: {
            q: busca,
            area: area || undefined,
            status: "ativa",
            limit: 30,
          },
        });
        setTeses(data.teses ?? []);
      } else {
        const { data } = await api.get("/teses/busca-avancada", {
          params: { area: area || undefined, status: "ativa", limit: 30 },
        });
        setTeses(data.teses ?? []);
      }
    } finally {
      setLoading(false);
    }
  }, [busca, area]);

  const carregarMemorias = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { limit: "30" };
      if (busca.trim()) params.q = busca;
      if (area) params.area = area;
      const { data } = await api.get("/memoria-institucional", { params });
      const estrategias = (data as Memoria[]).filter(
        (m) =>
          ["estrategia", "tese_vencedora", "acordo"].includes(m.tipo) ||
          m.resultado === "favoravel",
      );
      setMemorias(estrategias);
    } finally {
      setLoading(false);
    }
  }, [busca, area]);

  useEffect(() => {
    if (aba === "teses") carregarTeses();
    else carregarMemorias();
  }, [aba, busca, area]);

  // Stats iniciais
  useEffect(() => {
    Promise.all([
      api.get("/teses/busca-avancada", {
        params: { status: "ativa", limit: 1 },
      }),
      api.get("/memoria-institucional", { params: { limit: "1" } }),
    ])
      .then(([t, m]) => {
        setStats({
          teses: t.data.total ?? 0,
          estrategias: (m.data as Memoria[]).filter(
            (x) => x.resultado === "favoravel",
          ).length,
          sucesso_medio:
            teses.reduce((a, t) => a + (t.taxa_sucesso ?? 0), 0) /
            (teses.length || 1),
        });
      })
      .catch(() => {});
  }, []);

  const buscar = () => setBusca(buscaInput);

  return (
    <div className="space-y-5 animate-rise">
      <PageHeader
        title="Biblioteca de Estratégias"
        subtitle="Teses jurídicas, precedentes vencedores e estratégias consolidadas do escritório"
        actions={
          <button
            className="btn-gold"
            onClick={() => (window.location.href = "/conhecimento")}
          >
            <Plus className="w-4 h-4" /> Ingerir na base RAG
          </button>
        }
      />

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="card p-4 flex items-center gap-3">
          <Scale className="w-5 h-5 text-bronze flex-shrink-0" />
          <div>
            <p className="font-serif text-xl text-navy-800">{stats.teses}</p>
            <p className="label-caps">teses ativas</p>
          </div>
        </div>
        <div className="card p-4 flex items-center gap-3">
          <CheckCircle className="w-5 h-5 text-success-500 flex-shrink-0" />
          <div>
            <p className="font-serif text-xl text-navy-800">
              {stats.estrategias}
            </p>
            <p className="label-caps">precedentes favoráveis</p>
          </div>
        </div>
        <div className="card p-4 flex items-center gap-3">
          <TrendingUp className="w-5 h-5 text-warn-500 flex-shrink-0" />
          <div>
            <p className="font-serif text-xl text-navy-800">
              {teses.length > 0
                ? (
                    teses.reduce((a, t) => a + (t.taxa_sucesso ?? 0), 0) /
                    teses.length
                  ).toFixed(0)
                : "—"}
              %
            </p>
            <p className="label-caps">sucesso médio</p>
          </div>
        </div>
      </div>

      {/* Busca e filtros */}
      <div className="flex gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
          <input
            className="input pl-9 pr-10"
            placeholder="Buscar tese, argumento, fundamento legal…"
            value={buscaInput}
            onChange={(e) => setBuscaInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && buscar()}
          />
          {buscaInput && (
            <button
              onClick={() => {
                setBuscaInput("");
                setBusca("");
              }}
              className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
        <select
          className="input w-44"
          value={area}
          onChange={(e) => setArea(e.target.value)}
        >
          <option value="">Todas as áreas</option>
          {Object.entries(AREA_LABELS).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        <button className="btn-primary" onClick={buscar}>
          <Search className="w-4 h-4" />
          Buscar
        </button>
      </div>

      {/* Abas */}
      <div className="flex gap-1 bg-bronze-50/60 rounded-xl p-1 w-fit">
        {(["teses", "estrategias"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setAba(t)}
            className={`px-4 py-1.5 rounded-lg text-sm transition-all ${
              aba === t
                ? "bg-white text-navy-800 shadow-sm font-normal"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {t === "teses" ? "Teses Jurídicas" : "Precedentes do Escritório"}
          </button>
        ))}
      </div>

      {/* Conteúdo */}
      {loading ? (
        <Spinner />
      ) : aba === "teses" ? (
        <div className="space-y-2">
          {teses.length === 0 && (
            <div className="card p-8 text-center">
              <BookOpen className="w-8 h-8 text-slate-300 mx-auto mb-3" />
              <p className="text-sm text-slate-400">Nenhuma tese encontrada.</p>
              <p className="text-xs text-slate-300 mt-1">
                Adicione teses via IA Jurídica → Sugerir Teses
              </p>
            </div>
          )}
          {teses.map((t) => (
            <CardTese key={t.id} t={t} onClick={() => setTeseSelecionada(t)} />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {memorias.length === 0 && (
            <div className="card p-8 text-center">
              <CheckCircle className="w-8 h-8 text-slate-300 mx-auto mb-3" />
              <p className="text-sm text-slate-400">
                Nenhum precedente registrado.
              </p>
              <p className="text-xs text-slate-300 mt-1">
                Registre estratégias e resultados via Memória Institucional
              </p>
            </div>
          )}
          {memorias.map((m) => (
            <CardMemoria key={m.id} m={m} />
          ))}
        </div>
      )}

      {/* Modal detalhe tese */}
      {teseSelecionada && (
        <ModalTese
          tese={teseSelecionada}
          onClose={() => setTeseSelecionada(null)}
        />
      )}
    </div>
  );
}
