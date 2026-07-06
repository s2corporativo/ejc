import { useEffect, useState, useCallback } from "react";
import {
  BookMarked,
  Plus,
  Search,
  X,
  ChevronDown,
  ChevronUp,
  Scale,
  FileText,
  Gavel,
  Handshake,
  Lightbulb,
  CheckCircle,
  XCircle,
  MinusCircle,
  Clock,
  Filter,
  Tag,
  Calendar,
  Edit3,
  Trash2,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "../components/Toast";
import { PageHeader, Spinner, fmtDate } from "../components/UI";
import { Markdown } from "../components/Markdown";

// ─── Tipos ────────────────────────────────────────────────────────────────────
interface Memoria {
  id: string;
  titulo: string;
  conteudo: string;
  tipo: string;
  resultado: string;
  area_direito: string;
  tags: string[];
  created_at: string;
  case_id?: string;
  advogado_id?: string;
}

const TIPOS: Record<
  string,
  { label: string; icon: React.ElementType; cor: string }
> = {
  peticao: {
    label: "Petição",
    icon: FileText,
    cor: "bg-navy-50 text-navy-600",
  },
  recurso: {
    label: "Recurso",
    icon: Scale,
    cor: "bg-primary-50 text-primary-600",
  },
  parecer: {
    label: "Parecer",
    icon: BookMarked,
    cor: "bg-warn-50 text-warn-700",
  },
  contrato: {
    label: "Contrato",
    icon: FileText,
    cor: "bg-slate-100 text-slate-600",
  },
  decisao: {
    label: "Decisão",
    icon: Gavel,
    cor: "bg-bronze-50 text-bronze-deep",
  },
  acordo: {
    label: "Acordo",
    icon: Handshake,
    cor: "bg-success-50 text-success-700",
  },
  tese_vencedora: {
    label: "Tese vencedora",
    icon: CheckCircle,
    cor: "bg-success-50 text-success-700",
  },
  estrategia: {
    label: "Estratégia",
    icon: Lightbulb,
    cor: "bg-warn-50 text-warn-700",
  },
};

const RESULTADOS: Record<
  string,
  { label: string; badge: string; icon: React.ElementType }
> = {
  favoravel: { label: "Favorável", badge: "badge-success", icon: CheckCircle },
  desfavoravel: { label: "Desfavorável", badge: "badge-danger", icon: XCircle },
  parcial: { label: "Parcial", badge: "badge-warn", icon: MinusCircle },
  acordo: { label: "Acordo", badge: "badge-info", icon: Handshake },
  em_andamento: { label: "Em andamento", badge: "badge-neutral", icon: Clock },
};

const AREAS: Record<string, string> = {
  civel: "Cível",
  trabalhista: "Trabalhista",
  penal: "Penal",
  empresarial: "Empresarial",
  administrativo: "Administrativo",
  bancario: "Bancário",
  tributario: "Tributário",
  ambiental: "Ambiental",
};

// ─── Card de memória ──────────────────────────────────────────────────────────
function CardMemoria({
  m,
  onEditar,
  onExcluir,
}: {
  m: Memoria;
  onEditar: () => void;
  onExcluir: () => void;
}) {
  const [expandido, setExpandido] = useState(false);
  const tipo = TIPOS[m.tipo] ?? {
    label: m.tipo,
    icon: FileText,
    cor: "bg-slate-100 text-slate-600",
  };
  const resultado = m.resultado ? RESULTADOS[m.resultado] : null;
  const Icon = tipo.icon;
  const previewTexto =
    m.conteudo.length > 200 ? m.conteudo.slice(0, 200) + "…" : m.conteudo;

  return (
    <div className="card overflow-hidden">
      <div className="p-4">
        <div className="flex items-start gap-3">
          <div className={`p-2 rounded-lg flex-shrink-0 mt-0.5 ${tipo.cor}`}>
            <Icon className="w-4 h-4" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <h3 className="font-serif text-base text-navy-800 leading-snug">
                {m.titulo}
              </h3>
              <div className="flex items-center gap-1 flex-shrink-0">
                {resultado && (
                  <span className={`badge ${resultado.badge} text-[10px]`}>
                    {resultado.label}
                  </span>
                )}
                <button
                  onClick={onEditar}
                  className="p-1.5 text-slate-400 hover:text-bronze rounded-lg transition-colors"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={onExcluir}
                  className="p-1.5 text-slate-400 hover:text-danger-500 rounded-lg transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 mt-1.5">
              <span className={`badge text-[10px] ${tipo.cor}`}>
                {tipo.label}
              </span>
              {m.area_direito && (
                <span className="badge badge-neutral text-[10px]">
                  {AREAS[m.area_direito] ?? m.area_direito}
                </span>
              )}
              <span className="flex items-center gap-1 text-[11px] text-slate-400">
                <Calendar className="w-3 h-3" /> {fmtDate(m.created_at)}
              </span>
            </div>

            {/* Conteúdo */}
            <div className="mt-3">
              {expandido ? (
                <Markdown
                  source={m.conteudo}
                  className="text-sm text-slate-600 leading-relaxed prose-sm"
                />
              ) : (
                <p className="text-sm text-slate-500 leading-relaxed">
                  {previewTexto}
                </p>
              )}
              {m.conteudo.length > 200 && (
                <button
                  onClick={() => setExpandido(!expandido)}
                  className="flex items-center gap-1 text-xs text-bronze hover:text-bronze-dark mt-2 transition-colors"
                >
                  {expandido ? (
                    <>
                      <ChevronUp className="w-3 h-3" /> Ver menos
                    </>
                  ) : (
                    <>
                      <ChevronDown className="w-3 h-3" /> Ver completo
                    </>
                  )}
                </button>
              )}
            </div>

            {/* Tags */}
            {m.tags?.length > 0 && (
              <div className="flex gap-1 mt-2.5 flex-wrap">
                {m.tags.map((t) => (
                  <span
                    key={t}
                    className="inline-flex items-center gap-0.5 text-[10px] text-bronze-deep bg-bronze-50 px-1.5 py-0.5 rounded"
                  >
                    <Tag className="w-2 h-2" /> {t}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Modal criar/editar ───────────────────────────────────────────────────────
interface FormData {
  titulo: string;
  conteudo: string;
  tipo: string;
  resultado: string;
  area_direito: string;
  tags: string;
}

function ModalForm({
  initial,
  onSalvo,
  onClose,
}: {
  initial?: Partial<FormData> & { id?: string };
  onSalvo: () => void;
  onClose: () => void;
}) {
  const [form, setForm] = useState<FormData>({
    titulo: initial?.titulo ?? "",
    conteudo: initial?.conteudo ?? "",
    tipo: initial?.tipo ?? "estrategia",
    resultado: initial?.resultado ?? "",
    area_direito: initial?.area_direito ?? "",
    tags: Array.isArray((initial as any)?.tags)
      ? (initial as any).tags.join(", ")
      : (initial?.tags ?? ""),
  });
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  const set = (k: keyof FormData, v: string) =>
    setForm((f) => ({ ...f, [k]: v }));

  const salvar = async () => {
    if (!form.titulo.trim()) {
      setErro("Título obrigatório");
      return;
    }
    if (form.conteudo.trim().length < 20) {
      setErro("Conteúdo muito curto");
      return;
    }
    setSalvando(true);
    setErro("");
    const payload = {
      ...form,
      tags: form.tags
        ? form.tags
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean)
        : [],
    };
    try {
      if (initial?.id) {
        await api.patch(`/memoria-institucional/${initial.id}`, payload);
      } else {
        await api.post("/memoria-institucional", payload);
      }
      onSalvo();
      onClose();
    } catch (e: any) {
      setErro(e.response?.data?.detail ?? "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="bg-white rounded-2xl shadow-float max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-bronze-pale flex items-center justify-between">
          <h2 className="font-serif text-lg text-navy-800">
            {initial?.id ? "Editar registro" : "Novo registro"}
          </h2>
          <button onClick={onClose} className="btn-ghost p-2">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-6 space-y-4">
          <div>
            <label className="label">Título *</label>
            <input
              className="input"
              value={form.titulo}
              onChange={(e) => set("titulo", e.target.value)}
              placeholder="Ex: Tese de nulidade por ausência de fundamentação…"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Tipo</label>
              <select
                className="input"
                value={form.tipo}
                onChange={(e) => set("tipo", e.target.value)}
              >
                {Object.entries(TIPOS).map(([v, { label }]) => (
                  <option key={v} value={v}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Resultado</label>
              <select
                className="input"
                value={form.resultado}
                onChange={(e) => set("resultado", e.target.value)}
              >
                <option value="">— sem resultado —</option>
                {Object.entries(RESULTADOS).map(([v, { label }]) => (
                  <option key={v} value={v}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="label">Área do direito</label>
            <select
              className="input"
              value={form.area_direito}
              onChange={(e) => set("area_direito", e.target.value)}
            >
              <option value="">— todas —</option>
              {Object.entries(AREAS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">
              Conteúdo *{" "}
              <span className="normal-case text-slate-400 font-light">
                (markdown suportado)
              </span>
            </label>
            <textarea
              className="input min-h-[180px] font-mono text-xs leading-relaxed"
              value={form.conteudo}
              onChange={(e) => set("conteudo", e.target.value)}
              placeholder={
                "# Tese\n\nDescreva a estratégia ou fundamento.\n\n## Argumentos\n\n- Argumento 1\n- Argumento 2\n\n## Base legal\n\nArt. X da Lei Y"
              }
            />
          </div>
          <div>
            <label className="label">
              Tags{" "}
              <span className="normal-case font-light text-slate-400">
                (separadas por vírgula)
              </span>
            </label>
            <input
              className="input"
              value={form.tags}
              onChange={(e) => set("tags", e.target.value)}
              placeholder="ex: recurso, multa ambiental, IBAMA"
            />
          </div>
          {erro && (
            <p className="text-sm text-danger-600 bg-danger-50 p-3 rounded-lg">
              {erro}
            </p>
          )}
          <div className="flex gap-3 pt-2">
            <button className="btn-ghost flex-1" onClick={onClose}>
              Cancelar
            </button>
            <button
              className="btn-primary flex-1"
              onClick={salvar}
              disabled={salvando}
            >
              {salvando
                ? "Salvando…"
                : initial?.id
                  ? "Salvar alterações"
                  : "Criar registro"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Página ───────────────────────────────────────────────────────────────────
export default function MemoriaInstitucional() {
  const [memorias, setMemorias] = useState<Memoria[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalAberto, setModalAberto] = useState(false);
  const [editando, setEditando] = useState<Memoria | null>(null);
  const [q, setQ] = useState("");
  const [qInput, setQInput] = useState("");
  const [tipo, setTipo] = useState("");
  const [resultado, setResultado] = useState("");
  const [area, setArea] = useState("");

  const carregar = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { limit: "50" };
      if (q) params.q = q;
      if (tipo) params.tipo = tipo;
      if (area) params.area = area;
      const { data } = await api.get("/memoria-institucional", { params });
      let lista = data as Memoria[];
      if (resultado) lista = lista.filter((m) => m.resultado === resultado);
      setMemorias(lista);
    } finally {
      setLoading(false);
    }
  }, [q, tipo, area, resultado]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const excluir = async (id: string) => {
    if (!confirm("Excluir este registro permanentemente?")) return;
    try {
      await api.delete(`/memoria-institucional/${id}`);
      carregar();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao excluir registro");
    }
  };

  const grupos = Object.entries(TIPOS)
    .map(([key, meta]) => ({
      key,
      meta,
      itens: memorias.filter((m) => m.tipo === key),
    }))
    .filter((g) => g.itens.length > 0);

  const resultadosFavoraveis = memorias.filter(
    (m) => m.resultado === "favoravel",
  ).length;

  return (
    <div className="space-y-5 animate-rise">
      <PageHeader
        title="Memória Institucional"
        subtitle="Repositório de estratégias, teses vencedoras, pareceres e acordos do escritório"
        actions={
          <button className="btn-gold" onClick={() => setModalAberto(true)}>
            <Plus className="w-4 h-4" /> Novo registro
          </button>
        }
      />

      {/* Stats rápidos */}
      <div className="grid grid-cols-3 gap-3">
        <div className="card p-4 flex items-center gap-3">
          <BookMarked className="w-4 h-4 text-bronze" />
          <div>
            <p className="font-serif text-xl text-navy-800">
              {memorias.length}
            </p>
            <p className="label-caps">registros</p>
          </div>
        </div>
        <div className="card p-4 flex items-center gap-3">
          <CheckCircle className="w-4 h-4 text-success-500" />
          <div>
            <p className="font-serif text-xl text-success-700">
              {resultadosFavoraveis}
            </p>
            <p className="label-caps">favoráveis</p>
          </div>
        </div>
        <div className="card p-4 flex items-center gap-3">
          <Lightbulb className="w-4 h-4 text-warn-500" />
          <div>
            <p className="font-serif text-xl text-warn-700">
              {
                memorias.filter(
                  (m) => m.tipo === "estrategia" || m.tipo === "tese_vencedora",
                ).length
              }
            </p>
            <p className="label-caps">estratégias</p>
          </div>
        </div>
      </div>

      {/* Filtros */}
      <div className="flex flex-wrap gap-2">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
          <input
            className="input pl-9"
            placeholder="Buscar por título ou conteúdo…"
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && setQ(qInput)}
          />
        </div>
        <select
          className="input w-40"
          value={tipo}
          onChange={(e) => setTipo(e.target.value)}
        >
          <option value="">Todos os tipos</option>
          {Object.entries(TIPOS).map(([v, { label }]) => (
            <option key={v} value={v}>
              {label}
            </option>
          ))}
        </select>
        <select
          className="input w-40"
          value={resultado}
          onChange={(e) => setResultado(e.target.value)}
        >
          <option value="">Todos os resultados</option>
          {Object.entries(RESULTADOS).map(([v, { label }]) => (
            <option key={v} value={v}>
              {label}
            </option>
          ))}
        </select>
        <select
          className="input w-40"
          value={area}
          onChange={(e) => setArea(e.target.value)}
        >
          <option value="">Todas as áreas</option>
          {Object.entries(AREAS).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        {(q || tipo || resultado || area) && (
          <button
            className="btn-ghost text-xs"
            onClick={() => {
              setQ("");
              setQInput("");
              setTipo("");
              setResultado("");
              setArea("");
            }}
          >
            <X className="w-3 h-3" /> Limpar
          </button>
        )}
      </div>

      {/* Lista */}
      {loading ? (
        <Spinner />
      ) : memorias.length === 0 ? (
        <div className="card p-10 text-center">
          <BookMarked className="w-10 h-10 text-slate-200 mx-auto mb-3" />
          <p className="text-sm text-slate-400 mb-1">
            Nenhum registro encontrado
          </p>
          <button
            className="btn-gold mt-3"
            onClick={() => setModalAberto(true)}
          >
            <Plus className="w-4 h-4" /> Criar primeiro registro
          </button>
        </div>
      ) : q || tipo || resultado || area ? (
        /* Vista plana quando há filtros */
        <div className="space-y-2">
          {memorias.map((m) => (
            <CardMemoria
              key={m.id}
              m={m}
              onEditar={() => setEditando(m)}
              onExcluir={() => excluir(m.id)}
            />
          ))}
        </div>
      ) : (
        /* Vista agrupada por tipo */
        <div className="space-y-4">
          {grupos.map(({ key, meta, itens }) => (
            <div key={key}>
              <div className="flex items-center gap-2 mb-2">
                <meta.icon className="w-3.5 h-3.5 text-bronze" />
                <p className="eyebrow">
                  {meta.label}{" "}
                  <span className="ml-1 text-slate-400">({itens.length})</span>
                </p>
              </div>
              <div className="space-y-2">
                {itens.map((m) => (
                  <CardMemoria
                    key={m.id}
                    m={m}
                    onEditar={() => setEditando(m)}
                    onExcluir={() => excluir(m.id)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modais */}
      {(modalAberto || editando) && (
        <ModalForm
          initial={
            editando
              ? {
                  id: editando.id,
                  titulo: editando.titulo,
                  conteudo: editando.conteudo,
                  tipo: editando.tipo,
                  resultado: editando.resultado,
                  area_direito: editando.area_direito,
                  tags: (editando.tags ?? []).join(", "),
                }
              : undefined
          }
          onSalvo={carregar}
          onClose={() => {
            setModalAberto(false);
            setEditando(null);
          }}
        />
      )}
    </div>
  );
}
