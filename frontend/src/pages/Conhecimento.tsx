import { useEffect, useState, useRef } from "react";
import { toast } from "../components/Toast";
import {
  Plus,
  Search,
  BookOpen,
  Trash2,
  FileText,
  Scale,
  Gavel,
  ScrollText,
  Library,
  Sparkles,
  CheckCircle2,
  Clock,
  AlertCircle,
  Filter,
  X,
  Download,
} from "lucide-react";
import api from "../lib/api";
import {
  PageHeader,
  Empty,
  ErrorState,
  Spinner,
  fmtDate,
} from "../components/UI";
import { asList } from "../lib/list";

// ── Categorias ────────────────────────────────────────────────────────────────
const CATS: { value: string; label: string; icon: any; cor: string }[] = [
  {
    value: "peca_escritorio",
    label: "Peça do escritório",
    icon: FileText,
    cor: "bg-navy/10 text-navy",
  },
  {
    value: "precedente_interno",
    label: "Tese vencedora",
    icon: Scale,
    cor: "bg-bronze-50 text-bronze-deep",
  },
  {
    value: "sumula_tst",
    label: "Súmula TST",
    icon: Gavel,
    cor: "bg-ai-100 text-ai-700",
  },
  {
    value: "sumula_stj",
    label: "Súmula STJ",
    icon: Gavel,
    cor: "bg-primary-100 text-primary-700",
  },
  {
    value: "sumula_stf",
    label: "Súmula STF",
    icon: Gavel,
    cor: "bg-primary-100 text-primary-700",
  },
  {
    value: "jurisprudencia",
    label: "Jurisprudência",
    icon: ScrollText,
    cor: "bg-warn-100 text-warn-700",
  },
  {
    value: "legislacao",
    label: "Legislação",
    icon: Library,
    cor: "bg-success-100 text-success-700",
  },
  {
    value: "doutrina",
    label: "Doutrina",
    icon: BookOpen,
    cor: "bg-slate-100 text-slate-600",
  },
];

const catMeta = (v: string) => CATS.find((c) => c.value === v) ?? CATS[7];

// ── Status badge ─────────────────────────────────────────────────────────────
function StatusBadge({ status }: { status: string }) {
  if (status === "indexado")
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-success-700 bg-success-50 px-2 py-0.5 rounded-full">
        <CheckCircle2 size={10} />
        Vetorizado
      </span>
    );
  if (status === "pendente")
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-warn-700 bg-warn-50 px-2 py-0.5 rounded-full">
        <Clock size={10} />
        Pendente
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
      <AlertCircle size={10} />
      Sem vetor
    </span>
  );
}

// ── Estimativa de chunks ──────────────────────────────────────────────────────
function estimarChunks(texto: string) {
  if (!texto) return 0;
  if (texto.length <= 1200) return 1;
  let n = 0,
    i = 0;
  while (i < texto.length) {
    n++;
    i += 1050;
  }
  return n;
}

// ── Modal de ingestão ─────────────────────────────────────────────────────────
function ModalIngestao({
  open,
  onClose,
  onSalvo,
}: {
  open: boolean;
  onClose: () => void;
  onSalvo: () => void;
}) {
  const [form, setForm] = useState({
    titulo: "",
    categoria: "peca_escritorio",
    fonte: "",
    tribunal: "",
    conteudo: "",
  });
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) {
      setForm({
        titulo: "",
        categoria: "peca_escritorio",
        fonte: "",
        tribunal: "",
        conteudo: "",
      });
      setErro("");
    }
  }, [open]);
  useEffect(() => {
    if (open) setTimeout(() => taRef.current?.focus(), 100);
  }, [open]);

  if (!open) return null;

  const chunks = estimarChunks(form.conteudo);
  const palavras = form.conteudo.trim().split(/\s+/).filter(Boolean).length;

  const salvar = async () => {
    if (!form.titulo.trim()) {
      setErro("Título obrigatório");
      return;
    }
    if (form.conteudo.trim().length < 50) {
      setErro("Conteúdo muito curto (mín. 50 caracteres)");
      return;
    }
    setSalvando(true);
    setErro("");
    try {
      await api.post("/rag/ingest", {
        titulo: form.titulo.trim(),
        categoria: form.categoria,
        conteudo: form.conteudo.trim(),
        ...(form.fonte ? { fonte: form.fonte } : {}),
        ...(form.tribunal ? { tribunal: form.tribunal } : {}),
      });
      onSalvo();
      onClose();
    } catch (e: any) {
      setErro(e.response?.data?.detail || "Erro ao ingerir");
    } finally {
      setSalvando(false);
    }
  };

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/45" onClick={onClose} />
      <div className="relative bg-white border border-slate-200 rounded-2xl shadow-float w-full max-w-3xl max-h-[92vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-bronze-50">
          <div>
            <h2 className="font-serif font-bold text-navy text-lg">
              Adicionar à base de conhecimento
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Cole o texto da peça, tese ou súmula — a IA usará nas próximas
              gerações
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-100 text-slate-400"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          {/* Categoria — seleção visual */}
          <div>
            <label className="label mb-2">Tipo de conteúdo</label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {CATS.map((c) => {
                const Icon = c.icon;
                const sel = form.categoria === c.value;
                return (
                  <button
                    key={c.value}
                    type="button"
                    onClick={() => set("categoria", c.value)}
                    className={`flex items-center gap-2 px-3 py-2.5 rounded-xl border text-left text-sm font-medium transition-all ${
                      sel
                        ? "border-navy bg-navy text-white shadow-sm"
                        : "border-slate-200 hover:border-bronze text-slate-600"
                    }`}
                  >
                    <Icon size={14} className={sel ? "text-white" : ""} />
                    <span className="truncate text-xs">{c.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Título */}
          <div>
            <label className="label">Título *</label>
            <input
              className="input"
              placeholder="Ex: Recurso Ordinário — dano moral assédio — TRT3 2024 (ganho)"
              value={form.titulo}
              onChange={(e) => set("titulo", e.target.value)}
            />
          </div>

          {/* Fonte + Tribunal */}
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="label">Fonte / referência</label>
              <input
                className="input"
                placeholder="Ex: TRT3 — RO 0001234-12.2024"
                value={form.fonte}
                onChange={(e) => set("fonte", e.target.value)}
              />
            </div>
            <div>
              <label className="label">Tribunal</label>
              <input
                className="input"
                placeholder="Ex: TRT3, STJ, TST"
                value={form.tribunal}
                onChange={(e) => set("tribunal", e.target.value)}
              />
            </div>
          </div>

          {/* Conteúdo */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="label">Conteúdo *</label>
              {form.conteudo && (
                <span className="text-xs text-slate-400">
                  {palavras} palavras · {form.conteudo.length} chars · {chunks}{" "}
                  chunk{chunks !== 1 ? "s" : ""}
                </span>
              )}
            </div>
            <textarea
              ref={taRef}
              rows={14}
              className="input font-mono text-xs resize-y min-h-[200px]"
              placeholder={`Cole aqui o texto completo da peça, tese, súmula ou ementa...\n\nDica: quanto mais completo o texto, melhor a IA vai encontrá-lo nas buscas semânticas.`}
              value={form.conteudo}
              onChange={(e) => set("conteudo", e.target.value)}
            />
          </div>

          {erro && (
            <div className="text-sm text-danger-600 bg-danger-50 border border-danger-200 rounded-xl px-4 py-3">
              {erro}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-bronze-50 bg-slate-50/50 rounded-b-2xl">
          <div className="text-xs text-slate-400">
            {chunks > 1
              ? `Texto longo — será dividido em ${chunks} blocos para busca`
              : "Será indexado como 1 bloco"}
          </div>
          <div className="flex gap-3">
            <button onClick={onClose} className="btn btn-ghost">
              Cancelar
            </button>
            <button
              onClick={salvar}
              disabled={salvando}
              className="btn btn-primary gap-2"
            >
              {salvando ? (
                "Ingerindo..."
              ) : (
                <>
                  <Sparkles size={15} />
                  Adicionar à base
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Modal ingestão PDF / URL ──────────────────────────────────────────────────
function ModalIngestPdf({
  modo,
  onClose,
  onSalvo,
}: {
  modo: "pdf" | "url";
  onClose: () => void;
  onSalvo: () => void;
}) {
  const [titulo, setTitulo] = useState("");
  const [categoria, setCategoria] = useState("jurisprudencia");
  const [tribunal, setTribunal] = useState("");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");
  const [resultado, setResultado] = useState<any>(null);

  const enviar = async () => {
    if (!titulo.trim()) {
      setErro("Título obrigatório");
      return;
    }
    setSalvando(true);
    setErro("");
    try {
      if (modo === "pdf") {
        if (!arquivo) {
          setErro("Selecione um arquivo PDF");
          setSalvando(false);
          return;
        }
        const fd = new FormData();
        fd.append("file", arquivo);
        fd.append("titulo", titulo);
        fd.append("categoria", categoria);
        if (tribunal) fd.append("tribunal", tribunal);
        const { data } = await api.post("/rag/ingest-pdf", fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        setResultado(data);
      } else {
        if (!url.trim()) {
          setErro("URL obrigatória");
          setSalvando(false);
          return;
        }
        const fd = new FormData();
        fd.append("url", url);
        fd.append("titulo", titulo);
        fd.append("categoria", categoria);
        if (tribunal) fd.append("tribunal", tribunal);
        const { data } = await api.post("/rag/ingest-url", fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        setResultado(data);
      }
      onSalvo();
    } catch (e: any) {
      setErro(e.response?.data?.detail ?? "Erro ao ingerir");
    } finally {
      setSalvando(false);
    }
  };

  if (!true) return null;

  return (
    <div className="modal-backdrop">
      <div className="bg-white rounded-2xl shadow-float max-w-lg w-full">
        <div className="px-6 py-4 border-b border-bronze-pale flex items-center justify-between">
          <h2 className="font-serif text-lg text-navy-800">
            {modo === "pdf" ? "Ingerir PDF na base RAG" : "Ingerir por URL"}
          </h2>
          <button onClick={onClose} className="btn-ghost p-2">
            <X size={16} />
          </button>
        </div>
        {resultado ? (
          <div className="p-6 text-center space-y-3">
            <CheckCircle2 className="w-10 h-10 text-success-500 mx-auto" />
            <p className="font-serif text-lg text-navy-800">
              Ingerido com sucesso!
            </p>
            <p className="text-sm text-slate-500">
              {resultado.paginas && <span>{resultado.paginas} páginas · </span>}
              {resultado.chunks} chunks ·{" "}
              {resultado.caracteres?.toLocaleString()} caracteres
            </p>
            <p className="text-xs text-slate-400">{resultado.detail}</p>
            <button className="btn-primary" onClick={onClose}>
              Fechar
            </button>
          </div>
        ) : (
          <div className="p-6 space-y-4">
            <div>
              <label className="label">Título *</label>
              <input
                className="input"
                value={titulo}
                onChange={(e) => setTitulo(e.target.value)}
                placeholder={
                  modo === "pdf"
                    ? "Ex: Acórdão STJ REsp 1.234.567"
                    : "Ex: Decisão TRT-MG proc. 0001234-56.2024"
                }
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Categoria</label>
                <select
                  className="input"
                  value={categoria}
                  onChange={(e) => setCategoria(e.target.value)}
                >
                  <option value="jurisprudencia">Jurisprudência</option>
                  <option value="sumula_stf">Súmula STF</option>
                  <option value="sumula_stj">Súmula STJ</option>
                  <option value="sumula_tst">Súmula TST</option>
                  <option value="legislacao">Legislação</option>
                  <option value="doutrina">Doutrina</option>
                  <option value="precedente_interno">Precedente interno</option>
                  <option value="peca_escritorio">Peça do escritório</option>
                </select>
              </div>
              <div>
                <label className="label">Tribunal</label>
                <input
                  className="input"
                  value={tribunal}
                  onChange={(e) => setTribunal(e.target.value)}
                  placeholder="Ex: STJ, TRT-3, TJMG"
                />
              </div>
            </div>
            {modo === "pdf" ? (
              <div>
                <label className="label">Arquivo PDF *</label>
                <input
                  type="file"
                  accept=".pdf"
                  onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
                  className="block w-full text-sm text-slate-500 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-medium file:bg-bronze-50 file:text-bronze-deep hover:file:bg-bronze-pale/60 cursor-pointer"
                />
                {arquivo && (
                  <p className="text-xs text-slate-400 mt-1">
                    {arquivo.name} ({(arquivo.size / 1024).toFixed(0)} KB)
                  </p>
                )}
              </div>
            ) : (
              <div>
                <label className="label">URL do documento *</label>
                <input
                  className="input"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://stj.jus.br/... ou https://trt3.jus.br/..."
                />
                <p className="text-[11px] text-slate-400 mt-1">
                  Suporta PDF direto ou página HTML de tribunal
                </p>
              </div>
            )}
            {erro && (
              <p className="text-sm text-danger-600 bg-danger-50 p-3 rounded-lg">
                {erro}
              </p>
            )}
            <div className="flex gap-3">
              <button className="btn-ghost flex-1" onClick={onClose}>
                Cancelar
              </button>
              <button
                className="btn-primary flex-1"
                onClick={enviar}
                disabled={salvando}
              >
                {salvando
                  ? "Processando…"
                  : modo === "pdf"
                    ? "Enviar PDF"
                    : "Ingerir URL"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Importar jurisprudência (APIs oficiais) ──────────────────────────────────
type FonteImportacao = {
  slug: string;
  nome: string;
  descricao: string;
  tribunais: string;
  enabled: boolean;
  ultima_execucao?: string | null;
  ultimo_status?: string | null;
  registros_novos?: number;
};

type ResumoImportacao = {
  importados: number;
  duplicados: number;
  erros: number;
};

function SecaoImportarJuris({ onImportado }: { onImportado: () => void }) {
  const [fontes, setFontes] = useState<FonteImportacao[]>([]);
  const [fonte, setFonte] = useState("");
  const [consulta, setConsulta] = useState("");
  const [tribunal, setTribunal] = useState("");
  const [limite, setLimite] = useState(20);
  const [importando, setImportando] = useState(false);
  const [resultado, setResultado] = useState<
    (ResumoImportacao & { encontrados?: number }) | null
  >(null);
  const [erro, setErro] = useState("");
  const vivoRef = useRef(true);

  useEffect(() => {
    vivoRef.current = true;
    api
      .get("/conhecimento/importar-jurisprudencia/fontes")
      .then((r) => {
        if (!vivoRef.current) return;
        const fs: FonteImportacao[] = asList(r.data.fontes ?? r.data);
        setFontes(fs);
        const ativa = fs.find((f) => f.enabled);
        if (ativa) setFonte(ativa.slug);
      })
      .catch(() => setFontes([]));
    return () => {
      vivoRef.current = false;
    };
  }, []);

  const aguardarJob = async (jobId: string) => {
    // Polling do status consultável do job (máx. ~3 min).
    for (let i = 0; i < 72; i++) {
      await new Promise((r) => setTimeout(r, 2500));
      if (!vivoRef.current) return null;
      try {
        const { data } = await api.get(
          `/conhecimento/importar-jurisprudencia/status/${jobId}`,
        );
        if (data.status !== "executando") return data;
      } catch (e: any) {
        // 404 = job não encontrado neste processo (backend reiniciado ou id
        // expirado) — parar o polling em vez de esperar o timeout de 3 min.
        if (e?.response?.status === 404) {
          return {
            status: "erro",
            erro: "Job não encontrado neste processo (backend reiniciado ou registro expirado). O resultado durável fica em fontes_ingestao/auditoria.",
          };
        }
        /* transiente — tenta de novo */
      }
    }
    return { status: "erro", erro: "Tempo limite de acompanhamento excedido" };
  };

  const importar = async () => {
    if (!fonte) {
      setErro("Selecione a fonte oficial");
      return;
    }
    if (consulta.trim().length < 3) {
      setErro("Informe a consulta/tema (mín. 3 caracteres)");
      return;
    }
    setErro("");
    setResultado(null);
    setImportando(true);
    try {
      const { data } = await api.post("/conhecimento/importar-jurisprudencia", {
        fonte,
        consulta: consulta.trim(),
        ...(tribunal.trim() ? { tribunal: tribunal.trim().toUpperCase() } : {}),
        limite,
      });
      const fim = await aguardarJob(data.job_id);
      if (!fim || !vivoRef.current) return;
      if (fim.status === "concluido") {
        const resumo: ResumoImportacao = fim.resumo ?? {
          importados: 0,
          duplicados: 0,
          erros: 0,
        };
        setResultado({ ...resumo, encontrados: fim.encontrados });
        toast.success(
          `Importação concluída: ${resumo.importados} novo(s), ${resumo.duplicados} duplicado(s)`,
        );
        if (resumo.importados > 0) onImportado();
      } else {
        setErro(fim.erro || "Falha na importação — tente novamente");
      }
    } catch (e: any) {
      setErro(
        e.response?.data?.detail?.toString?.() ||
          "Erro ao iniciar a importação",
      );
    } finally {
      if (vivoRef.current) setImportando(false);
    }
  };

  const fonteSel = fontes.find((f) => f.slug === fonte);

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between gap-2 mb-1">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
          Importar jurisprudência (APIs oficiais)
        </p>
        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-success-700 bg-success-50 px-2 py-0.5 rounded-full">
          <CheckCircle2 size={10} />
          Fontes oficiais — citações validadas
        </span>
      </div>
      <p className="text-[11px] text-slate-400 mb-3">
        Busca julgados reais em fontes públicas oficiais e alimenta a base de
        conhecimento e a base de citações verificáveis (dedup por
        tribunal+número).
      </p>
      <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
        <div className="md:col-span-3">
          <label className="label">Fonte oficial</label>
          <select
            className="input"
            value={fonte}
            onChange={(e) => setFonte(e.target.value)}
            disabled={importando}
          >
            {fontes.length === 0 && <option value="">Carregando…</option>}
            {fontes.map((f) => (
              <option key={f.slug} value={f.slug} disabled={!f.enabled}>
                {f.nome}
                {!f.enabled ? " (desativada)" : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="md:col-span-4">
          <label className="label">Consulta / tema *</label>
          <input
            className="input"
            placeholder="Ex: negativa de cobertura plano de saúde"
            value={consulta}
            onChange={(e) => setConsulta(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !importando && importar()}
            disabled={importando}
          />
        </div>
        <div className="md:col-span-2">
          <label className="label">Tribunal</label>
          <input
            className="input"
            placeholder="Ex: STJ"
            value={tribunal}
            onChange={(e) => setTribunal(e.target.value)}
            disabled={importando}
          />
        </div>
        <div className="md:col-span-1">
          <label className="label">Limite</label>
          <input
            className="input"
            type="number"
            min={1}
            max={100}
            value={limite}
            onChange={(e) =>
              setLimite(
                Math.max(1, Math.min(100, parseInt(e.target.value, 10) || 1)),
              )
            }
            disabled={importando}
          />
        </div>
        <div className="md:col-span-2 flex items-end">
          <button
            className="btn btn-primary w-full gap-2"
            onClick={importar}
            disabled={importando || !fonte}
          >
            {importando ? (
              <>
                <Spinner /> Importando…
              </>
            ) : (
              <>
                <Download size={15} />
                Importar
              </>
            )}
          </button>
        </div>
      </div>
      {fonteSel && (
        <p className="text-[11px] text-slate-400 mt-2">
          {fonteSel.descricao} · Cobertura: {fonteSel.tribunais}
          {fonteSel.ultima_execucao &&
            ` · Última importação: ${fmtDate(fonteSel.ultima_execucao)}`}
        </p>
      )}
      {erro && (
        <p className="text-sm text-danger-600 bg-danger-50 p-3 rounded-lg mt-3">
          {erro}
        </p>
      )}
      {resultado && (
        <div className="flex flex-wrap items-center gap-2 mt-3">
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-success-700 bg-success-50 px-2.5 py-1 rounded-full">
            <CheckCircle2 size={12} />
            {resultado.importados} importado(s)
          </span>
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-warn-700 bg-warn-50 px-2.5 py-1 rounded-full">
            <Clock size={12} />
            {resultado.duplicados} duplicado(s)
          </span>
          {resultado.erros > 0 && (
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-danger-600 bg-danger-50 px-2.5 py-1 rounded-full">
              <AlertCircle size={12} />
              {resultado.erros} erro(s)
            </span>
          )}
          {resultado.encontrados != null && (
            <span className="text-[11px] text-slate-400">
              {resultado.encontrados} julgado(s) localizados na fonte
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export default function Conhecimento() {
  const [docs, setDocs] = useState<any>(null);
  const [erroDocs, setErroDocs] = useState(false);
  const [total, setTotal] = useState(0);
  const [pagina, setPagina] = useState(1);
  const [catFiltro, setCatFiltro] = useState("");
  const [busca, setBusca] = useState("");
  const [buscaInput, setBuscaInput] = useState("");
  const [resultados, setResultados] = useState<any[] | null>(null);
  const [modal, setModal] = useState(false);
  const [modalPdf, setModalPdf] = useState<"pdf" | "url" | null>(null);
  const [removendo, setRemovendo] = useState<string | null>(null);

  const PER_PAGE = 30;

  const load = (pag = pagina, cat = catFiltro) => {
    setErroDocs(false);
    return api
      .get("/rag/docs", {
        params: {
          page: pag,
          page_size: PER_PAGE,
          ...(cat ? { categoria: cat } : {}),
        },
      })
      .then((r) => {
        setDocs(asList(r.data));
        setTotal(r.data.total ?? 0);
      })
      .catch(() => setErroDocs(true));
  };

  useEffect(() => {
    load(pagina, catFiltro);
  }, [pagina, catFiltro]);

  const buscar = async () => {
    if (buscaInput.length < 3) return;
    setBusca(buscaInput);
    const { data } = await api.get("/rag/buscar", {
      params: { q: buscaInput, limite: 8 },
    });
    setResultados(data.resultados ?? data);
  };

  const limparBusca = () => {
    setResultados(null);
    setBusca("");
    setBuscaInput("");
  };

  const remover = async (id: string) => {
    if (!confirm("Remover este documento da base de conhecimento?")) return;
    setRemovendo(id);
    try {
      await api.delete(`/rag/docs/${id}`);
      load();
    } catch {
      toast.error("Erro ao remover");
    } finally {
      setRemovendo(null);
    }
  };

  const totalPags = Math.ceil(total / PER_PAGE);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="IA Jurídica"
        title="Base de Conhecimento"
        subtitle="Peças vencedoras, teses e súmulas que a IA usa para gerar documentos quando estão vetorizadas (status por documento abaixo)"
        actions={
          <button
            className="btn btn-primary gap-2"
            onClick={() => setModal(true)}
          >
            <Plus size={15} />
            Adicionar conteúdo
          </button>
        }
      />

      {/* Busca semântica */}
      <div className="card p-5">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
          Consultar a base (busca semântica)
        </p>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search
              size={15}
              className="absolute left-3 top-2.5 text-slate-400"
            />
            <input
              className="input pl-9"
              placeholder="Ex: dano existencial jornada excessiva, usucapião requisitos..."
              value={buscaInput}
              onChange={(e) => setBuscaInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && buscar()}
            />
          </div>
          <button className="btn btn-primary" onClick={buscar}>
            Buscar
          </button>
          {resultados && (
            <button className="btn btn-ghost" onClick={limparBusca}>
              <X size={15} />
            </button>
          )}
        </div>

        {resultados && (
          <div className="mt-4 space-y-3">
            <p className="text-xs text-slate-500">
              {resultados.length} resultado(s) para "<b>{busca}</b>"
            </p>
            {resultados.length === 0 && (
              <p className="text-sm text-slate-400 py-4 text-center">
                Nenhum resultado — tente outros termos
              </p>
            )}
            {resultados.map((r, i) => {
              const cm = catMeta(r.categoria);
              return (
                <div
                  key={r.chunk_id ?? i}
                  className="border border-bronze-50 rounded-xl p-4"
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <span className="font-semibold text-navy text-sm">
                      {r.titulo}
                    </span>
                    <div className="flex items-center gap-2 shrink-0">
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${cm.cor}`}
                      >
                        {cm.label}
                      </span>
                      {r.similarity != null && (
                        <span className="text-[10px] font-semibold text-success-600 bg-success-50 px-2 py-0.5 rounded-full">
                          {Math.round(r.similarity * 100)}% similar
                        </span>
                      )}
                    </div>
                  </div>
                  <p className="text-sm text-slate-600 leading-relaxed">
                    {r.conteudo?.slice(0, 500)}
                    {(r.conteudo?.length ?? 0) > 500 && "…"}
                  </p>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Importar jurisprudência (APIs oficiais) */}
      <SecaoImportarJuris onImportado={() => load(1, catFiltro)} />

      {/* Filtros + lista */}
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <Filter size={14} className="text-slate-400" />
            <span className="text-sm text-slate-500">{total} documento(s)</span>
          </div>
          {/* Filtro por categoria */}
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => {
                setCatFiltro("");
                setPagina(1);
              }}
              className={`text-xs px-3 py-1.5 rounded-full font-medium transition-all ${!catFiltro ? "bg-navy text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
            >
              Todos
            </button>
            {CATS.map((c) => (
              <button
                key={c.value}
                onClick={() => {
                  setCatFiltro(c.value);
                  setPagina(1);
                }}
                className={`text-xs px-3 py-1.5 rounded-full font-medium transition-all ${catFiltro === c.value ? "bg-navy text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        {erroDocs ? (
          <ErrorState
            message="Não foi possível carregar a base de conhecimento. Tente novamente."
            onRetry={() => load()}
          />
        ) : !docs ? (
          <div className="flex justify-center py-10">
            <Spinner />
          </div>
        ) : docs.length === 0 ? (
          <Empty message="Nenhum documento encontrado" />
        ) : (
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b border-slate-100">
                <tr>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide">
                    Documento
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide hidden md:table-cell">
                    Tipo
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide hidden lg:table-cell">
                    Tribunal
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide hidden sm:table-cell">
                    Status
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide hidden lg:table-cell">
                    Adicionado
                  </th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {docs.map((d: any) => {
                  const cm = catMeta(d.categoria);
                  const Icon = cm.icon;
                  return (
                    <tr
                      key={d.id}
                      className="hover:bg-bronze-50/30 transition-colors"
                    >
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-3">
                          <div
                            className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${cm.cor}`}
                          >
                            <Icon size={13} />
                          </div>
                          <div className="min-w-0">
                            <p className="font-medium text-navy truncate max-w-xs">
                              {d.titulo}
                            </p>
                            {d.fonte && (
                              <p className="text-xs text-slate-400 truncate">
                                {d.fonte}
                              </p>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell">
                        <span
                          className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${cm.cor}`}
                        >
                          {cm.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-400 hidden lg:table-cell">
                        {d.tribunal || "—"}
                      </td>
                      <td className="px-4 py-3 hidden sm:table-cell">
                        <StatusBadge status={d.status_indexacao} />
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-400 hidden lg:table-cell">
                        {fmtDate(d.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => remover(d.id)}
                          disabled={removendo === d.id}
                          className="p-1.5 rounded-lg text-slate-300 hover:text-danger-500 hover:bg-danger-50 transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {/* Paginação */}
            {totalPags > 1 && (
              <div className="flex items-center justify-between px-5 py-3 border-t border-slate-100 bg-slate-50/50">
                <span className="text-xs text-slate-400">
                  Página {pagina} de {totalPags}
                </span>
                <div className="flex gap-2">
                  <button
                    disabled={pagina <= 1}
                    onClick={() => setPagina((p) => p - 1)}
                    className="btn btn-ghost text-xs px-3 py-1.5 disabled:opacity-40"
                  >
                    Anterior
                  </button>
                  <button
                    disabled={pagina >= totalPags}
                    onClick={() => setPagina((p) => p + 1)}
                    className="btn btn-ghost text-xs px-3 py-1.5 disabled:opacity-40"
                  >
                    Próxima
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <ModalIngestao
        open={modal}
        onClose={() => setModal(false)}
        onSalvo={() => {
          load(1, catFiltro);
          setPagina(1);
        }}
      />
      {modalPdf && (
        <ModalIngestPdf
          modo={modalPdf}
          onClose={() => setModalPdf(null)}
          onSalvo={() => {
            setModalPdf(null);
            load();
          }}
        />
      )}
    </div>
  );
}
