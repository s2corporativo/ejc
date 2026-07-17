import { useEffect, useState, useRef } from "react";
import { toast } from "../components/Toast";
import {
  Upload,
  Download,
  Search,
  Lock,
  Sparkles,
  Eye,
  Trash2,
  X,
} from "lucide-react";
import api from "../lib/api";
import {
  PageHeader,
  Modal,
  Empty,
  EmptyState,
  Spinner,
  Button,
  fmtDate,
} from "../components/UI";
import { DocumentosStats } from "../components/Dashboards";
import CaseFilterChip from "../components/CaseFilterChip";
import { useCasoFiltro } from "../contexts/useCasoFiltro";
import { asList } from "../lib/list";

/** Item de alternativa devolvido pela classificação por IA. */
type ClassAlternativa = { tipo_key: string; nome: string };

/** Shape de POST /documents/{id}/classificar (aplicar=false|true). */
type ClassResultado = {
  doc_id: string;
  aplicado: boolean;
  tipo_atual: string | null;
  tipo_sugerido: string | null;
  confianca: "alta" | "media" | "baixa" | null;
  alternativas: ClassAlternativa[];
  justificativa: string;
  disponivel: boolean;
  pii_removida?: boolean;
  modelo?: string;
  aviso?: string;
};

const CONF_LABEL: Record<string, string> = {
  alta: "Alta confiança",
  media: "Confiança média",
  baixa: "Baixa confiança",
};

// Espelho de EXTENSOES_PERMITIDAS do backend (documents.py).
const EXTS_UPLOAD = [
  ".pdf",
  ".docx",
  ".doc",
  ".jpg",
  ".jpeg",
  ".png",
  ".xlsx",
  ".xls",
  ".txt",
  ".xml",
];

// Formatos com pré-visualização inline (via GET /{id}/download como blob).
const EXTS_PREVIEW: Record<string, "pdf" | "img"> = {
  ".pdf": "pdf",
  ".jpg": "img",
  ".jpeg": "img",
  ".png": "img",
};

const extDe = (nome: string) => {
  const i = nome.lastIndexOf(".");
  return i >= 0 ? nome.slice(i).toLowerCase() : "";
};
const semExtensao = (nome: string) => {
  const i = nome.lastIndexOf(".");
  return i > 0 ? nome.slice(0, i) : nome;
};
const fmtKB = (bytes?: number) =>
  bytes ? `${(bytes / 1024).toFixed(0)} KB` : "—";

/** Arquivo aguardando envio no modal de upload (título editável por arquivo). */
type PendenteUpload = { file: File; titulo: string; erro?: string };

export default function Documentos() {
  const [data, setData] = useState<any>(null);
  const [search, setSearch] = useState("");
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<any>({ confidencialidade: "normal" });
  const fileRef = useRef<HTMLInputElement>(null);
  const [enviando, setEnviando] = useState(false);
  const [casos, setCasos] = useState<any[]>([]);

  // Upload múltiplo: fila de arquivos com título pré-preenchido (nome sem
  // extensão) e editável. O endpoint aceita 1 arquivo por chamada — o envio é
  // sequencial com progresso e resumo final.
  const [pendentes, setPendentes] = useState<PendenteUpload[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [progresso, setProgresso] = useState<{
    done: number;
    total: number;
  } | null>(null);

  // Filtro por cliente — GET /documents/ aceita client_id.
  const [clientes, setClientes] = useState<any[]>([]);
  const [clienteFiltro, setClienteFiltro] = useState("");

  // Pré-visualização sem download (blob de GET /{id}/download).
  const [preview, setPreview] = useState<{ doc: any; kind: "pdf" | "img" } | null>(
    null,
  );
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewErro, setPreviewErro] = useState<string | null>(null);

  // Seleção múltipla para ações em lote (baixar / excluir em sequência).
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [loteBusy, setLoteBusy] = useState<"download" | "delete" | null>(null);

  // Classificação de tipo por IA (sugerir → aplicar), confirmação humana obrigatória.
  const [classDoc, setClassDoc] = useState<any | null>(null);
  const [classResult, setClassResult] = useState<ClassResultado | null>(null);
  const [classLoading, setClassLoading] = useState(false);
  const [aplicando, setAplicando] = useState(false);

  const [erro, setErro] = useState(false);
  // Guarda de sequência: só a resposta mais recente aplica setData (evita que
  // a resposta antiga de uma busca com debounce sobrescreva a nova).
  const seq = useRef(0);

  // Modo Caso: `?caso=` na URL vence; sem query, o caso ativo preenche.
  // GET /documents/ já aceita case_id (fecha o GAP do link_modulo da jornada).
  const { casoFiltro, casoFiltroNome, removerFiltro } = useCasoFiltro();

  const load = () => {
    const my = ++seq.current;
    setErro(false);
    return api
      .get("/documents/", {
        params: {
          search: search || undefined,
          case_id: casoFiltro,
          client_id: clienteFiltro || undefined,
          page_size: 50,
        },
      })
      .then((r) => {
        if (my !== seq.current) return;
        setData(r.data);
        setSel(new Set()); // seleção sempre relativa à página carregada
      })
      .catch(() => {
        if (my !== seq.current) return;
        setErro(true);
        toast.error("Falha ao carregar documentos");
      });
  };
  useEffect(() => {
    // M12: lista de casos para vincular o documento (torna o gate IDOR efetivo).
    api
      .get("/cases/", { params: { page_size: 200 } })
      .then((r) => setCasos(asList(r.data)))
      .catch(() => {});
    // Clientes para o filtro por cliente (falha silenciosa: perfis sem acesso
    // a /clients/ simplesmente não veem o filtro populado).
    api
      .get("/clients/", { params: { page_size: 200 } })
      .then((r) => setClientes(asList(r.data)))
      .catch(() => {});
  }, []);
  useEffect(() => {
    const t = setTimeout(load, 350);
    return () => clearTimeout(t);
  }, [search, casoFiltro, clienteFiltro]);

  // ── Upload múltiplo ────────────────────────────────────────────────────────
  const adicionarArquivos = (lista: FileList | File[] | null) => {
    if (!lista) return;
    const novos: PendenteUpload[] = [];
    let ignorados = 0;
    Array.from(lista).forEach((f) => {
      if (!EXTS_UPLOAD.includes(extDe(f.name))) {
        ignorados += 1;
        return;
      }
      // Título automático: nome do arquivo sem a extensão (editável abaixo).
      novos.push({ file: f, titulo: semExtensao(f.name) });
    });
    if (ignorados > 0) {
      toast.error(
        `${ignorados} arquivo(s) ignorado(s): extensão não permitida`,
      );
    }
    if (novos.length > 0) setPendentes((p) => [...p, ...novos]);
  };

  const upload = async () => {
    if (pendentes.length === 0) {
      toast.error("Selecione ao menos um arquivo");
      return;
    }
    if (pendentes.some((p) => !p.titulo.trim())) {
      toast.error("Todo arquivo precisa de um título");
      return;
    }
    setEnviando(true);
    const falhas: PendenteUpload[] = [];
    const avisos: string[] = [];
    let ok = 0;
    // Endpoint aceita um arquivo por chamada → N chamadas sequenciais.
    for (let i = 0; i < pendentes.length; i++) {
      setProgresso({ done: i, total: pendentes.length });
      const p = pendentes[i];
      const fd = new FormData();
      fd.append("file", p.file);
      fd.append("titulo", p.titulo.trim());
      fd.append("confidencialidade", form.confidencialidade);
      if (form.tipo) fd.append("tipo", form.tipo);
      if (form.case_id) {
        fd.append("case_id", form.case_id);
        const caso = casos.find((c) => c.id === form.case_id);
        if (caso?.client_id) fd.append("client_id", caso.client_id);
      }
      try {
        const r = await api.post("/documents/upload", fd);
        ok += 1;
        // Backend avisa quando o formato legado (.doc/.xls) não é indexável.
        if (r.data?.aviso) avisos.push(`${p.titulo}: ${r.data.aviso}`);
      } catch (e: any) {
        falhas.push({
          ...p,
          erro: e.response?.data?.detail || "Erro no upload",
        });
      }
    }
    setProgresso(null);
    setEnviando(false);
    if (ok > 0) load();
    avisos.slice(0, 3).forEach((a) => toast.info(a));
    if (falhas.length === 0) {
      toast.success(
        ok === 1 ? "1 documento enviado" : `${ok} documentos enviados`,
      );
      setPendentes([]);
      setModal(false);
      setForm({ confidencialidade: "normal" });
    } else {
      toast.error(
        `${ok} enviado(s), ${falhas.length} falhou(aram) — revise os itens marcados e reenvie`,
      );
      // Mantém na fila apenas os que falharam, com o motivo por arquivo.
      setPendentes(falhas);
    }
  };

  // ── Download ───────────────────────────────────────────────────────────────
  const baixarBlob = async (d: any) => {
    const r = await api.get(`/documents/${d.id}/download`, {
      responseType: "blob",
    });
    const url = URL.createObjectURL(r.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = d.filename || d.titulo || "documento";
    a.click();
    URL.revokeObjectURL(url);
  };

  const baixar = async (d: any) => {
    try {
      await baixarBlob(d);
    } catch {
      toast.error(`Falha ao baixar "${d.titulo}"`);
    }
  };

  // ── Pré-visualização (sem download) ───────────────────────────────────────
  const abrirPreview = async (d: any) => {
    const kind = EXTS_PREVIEW[extDe(d.filename || "")];
    if (!kind) return;
    // Revoga a object URL de um preview anterior ainda aberto antes de trocar.
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreview({ doc: d, kind });
    setPreviewUrl(null);
    setPreviewErro(null);
    try {
      const r = await api.get(`/documents/${d.id}/download`, {
        responseType: "blob",
      });
      setPreviewUrl(URL.createObjectURL(r.data));
    } catch {
      setPreviewErro(
        "Não foi possível carregar a pré-visualização. Tente baixar o arquivo.",
      );
    }
  };

  const fecharPreview = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreview(null);
    setPreviewUrl(null);
    setPreviewErro(null);
  };

  // ── Seleção múltipla / ações em lote ──────────────────────────────────────
  const docs: any[] = Array.isArray(data?.data) ? data.data : [];
  const selDocs = docs.filter((d) => sel.has(d.id));
  const allSel = docs.length > 0 && docs.every((d) => sel.has(d.id));

  const toggleSel = (id: string) =>
    setSel((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const toggleSelAll = () =>
    setSel(allSel ? new Set() : new Set(docs.map((d) => d.id)));

  const baixarSelecionados = async () => {
    if (selDocs.length === 0) return;
    setLoteBusy("download");
    let ok = 0;
    const falhas: string[] = [];
    for (const d of selDocs) {
      try {
        await baixarBlob(d);
        ok += 1;
      } catch {
        falhas.push(d.titulo);
      }
    }
    setLoteBusy(null);
    if (falhas.length === 0) {
      toast.success(`${ok} documento(s) baixado(s)`);
    } else {
      toast.error(
        `${ok} baixado(s), ${falhas.length} falhou(aram): ${falhas
          .slice(0, 3)
          .join(", ")}${falhas.length > 3 ? "…" : ""}`,
      );
    }
  };

  const excluirSelecionados = async () => {
    if (selDocs.length === 0) return;
    if (
      !window.confirm(
        `Excluir ${selDocs.length} documento(s) selecionado(s)?`,
      )
    )
      return;
    setLoteBusy("delete");
    let ok = 0;
    const falhas: string[] = [];
    for (const d of selDocs) {
      try {
        await api.delete(`/documents/${d.id}`);
        ok += 1;
      } catch {
        falhas.push(d.titulo);
      }
    }
    setLoteBusy(null);
    setSel(new Set());
    load();
    if (falhas.length === 0) {
      toast.success(`${ok} documento(s) excluído(s)`);
    } else {
      toast.error(
        `${ok} excluído(s), ${falhas.length} falhou(aram): ${falhas
          .slice(0, 3)
          .join(", ")}${falhas.length > 3 ? "…" : ""}`,
      );
    }
  };

  const excluir = async (d: any) => {
    if (!window.confirm(`Excluir o documento "${d.titulo}"?`)) return;
    try {
      await api.delete(`/documents/${d.id}`);
      toast.success("Documento excluído");
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao excluir documento");
    }
  };

  // ── Classificação IA (HITL — inalterado) ──────────────────────────────────
  // Abre o modal e busca a SUGESTÃO de tipo (aplicar=false — nunca grava aqui).
  const classificar = async (doc: any) => {
    setClassDoc(doc);
    setClassResult(null);
    setClassLoading(true);
    try {
      const r = await api.post<ClassResultado>(
        `/documents/${doc.id}/classificar`,
        null,
        { params: { aplicar: false } },
      );
      setClassResult(r.data);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao classificar documento");
      setClassDoc(null);
    } finally {
      setClassLoading(false);
    }
  };

  // Persiste o tipo sugerido (aplicar=true) e atualiza a linha na UI.
  const aplicarTipo = async () => {
    if (!classDoc) return;
    setAplicando(true);
    try {
      const r = await api.post<ClassResultado>(
        `/documents/${classDoc.id}/classificar`,
        null,
        { params: { aplicar: true } },
      );
      const novoTipo = r.data.tipo_atual;
      setData((prev: any) =>
        prev
          ? {
              ...prev,
              data: (Array.isArray(prev.data) ? prev.data : []).map((d: any) =>
                d.id === classDoc.id ? { ...d, tipo: novoTipo } : d,
              ),
            }
          : prev,
      );
      toast.success(`Tipo aplicado: ${novoTipo || "—"}`);
      setClassDoc(null);
      setClassResult(null);
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao aplicar o tipo");
    } finally {
      setAplicando(false);
    }
  };

  const fecharClass = () => {
    setClassDoc(null);
    setClassResult(null);
  };

  const confIcon = (c: string) =>
    ["restrito", "confidencial", "segredo_justica"].includes(c) ? (
      <Lock size={13} className="text-danger-500" />
    ) : null;

  return (
    <div>
      <PageHeader
        title="Documentos"
        subtitle="GED do escritório"
        actions={
          <button
            className="btn-gold"
            onClick={() => {
              // Modo Caso: pré-seleciona o caso filtrado no vínculo do upload.
              if (casoFiltro && !form.case_id) {
                setForm((f: any) => ({ ...f, case_id: casoFiltro }));
              }
              setModal(true);
            }}
          >
            <Upload size={16} /> Enviar
          </button>
        }
      />

      <DocumentosStats />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-full max-w-md">
          <Search
            size={16}
            className="absolute left-3 top-2.5 text-slate-400"
          />
          <input
            className="input pl-9"
            placeholder="Buscar documento..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        {clientes.length > 0 && (
          <select
            className="input w-auto max-w-[220px] text-sm"
            value={clienteFiltro}
            onChange={(e) => setClienteFiltro(e.target.value)}
            title="Filtrar por cliente"
          >
            <option value="">Todos os clientes</option>
            {clientes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome || c.razao_social || "Cliente"}
              </option>
            ))}
          </select>
        )}
        {casoFiltro && (
          <CaseFilterChip nome={casoFiltroNome} onRemove={removerFiltro} />
        )}
      </div>

      {sel.size > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-primary-200 bg-primary-50/60 px-3 py-2 text-sm dark:border-primary-800 dark:bg-primary-900/20">
          <span className="font-medium text-navy">
            {sel.size} selecionado(s)
          </span>
          <button
            className="btn-ghost px-2 py-1"
            disabled={loteBusy !== null}
            onClick={baixarSelecionados}
          >
            <Download size={14} />
            {loteBusy === "download" ? "Baixando…" : "Baixar"}
          </button>
          <button
            className="btn-ghost px-2 py-1 text-danger-500"
            disabled={loteBusy !== null}
            onClick={excluirSelecionados}
          >
            <Trash2 size={14} />
            {loteBusy === "delete" ? "Excluindo…" : "Excluir"}
          </button>
          <button
            className="btn-ghost px-2 py-1"
            disabled={loteBusy !== null}
            onClick={() => setSel(new Set())}
          >
            <X size={14} /> Limpar seleção
          </button>
        </div>
      )}

      {erro && !data ? (
        <EmptyState
          title="Falha ao carregar documentos"
          message="Não foi possível carregar a lista. Verifique sua conexão e tente novamente."
          action={
            <Button variant="primary" onClick={load}>
              Tentar novamente
            </Button>
          }
        />
      ) : !data ? (
        <Spinner />
      ) : data.data.length === 0 ? (
        <Empty message="Nenhum documento" />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="w-8 px-3 py-3">
                  <input
                    type="checkbox"
                    checked={allSel}
                    onChange={toggleSelAll}
                    aria-label="Selecionar todos"
                  />
                </th>
                <th className="px-4 py-3">Título</th>
                <th className="px-4 py-3">Arquivo</th>
                <th className="px-4 py-3">Tipo</th>
                <th className="px-4 py-3">Confidencialidade</th>
                <th className="px-4 py-3">Tamanho</th>
                <th className="px-4 py-3">Enviado em</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {docs.map((d: any) => (
                <tr key={d.id} className="hover:bg-slate-50">
                  <td className="w-8 px-3 py-3">
                    <input
                      type="checkbox"
                      checked={sel.has(d.id)}
                      onChange={() => toggleSel(d.id)}
                      aria-label={`Selecionar ${d.titulo}`}
                    />
                  </td>
                  <td className="px-4 py-3 font-medium text-navy flex items-center gap-1.5">
                    {confIcon(d.confidencialidade)} {d.titulo}
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-xs">
                    {d.filename}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {d.tipo ? (
                      <span className="capitalize">
                        {String(d.tipo).replace(/_/g, " ")}
                      </span>
                    ) : (
                      <span
                        className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400"
                        title="Documento sem tipo definido — use a classificação por IA (✦) ou defina manualmente."
                      >
                        Classificação pendente
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 capitalize text-xs">
                    {d.confidencialidade.replace(/_/g, " ")}
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">
                    {fmtKB(d.size_bytes)}
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {fmtDate(d.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      {EXTS_PREVIEW[extDe(d.filename || "")] && (
                        <button
                          className="btn-ghost px-2 py-1"
                          title="Pré-visualizar"
                          onClick={() => abrirPreview(d)}
                        >
                          <Eye size={15} />
                        </button>
                      )}
                      <button
                        className="btn-ghost px-2 py-1"
                        title="Classificar tipo (IA)"
                        disabled={classLoading && classDoc?.id === d.id}
                        onClick={() => classificar(d)}
                      >
                        <Sparkles size={15} />
                      </button>
                      <button
                        className="btn-ghost px-2 py-1"
                        title="Baixar"
                        onClick={() => baixar(d)}
                      >
                        <Download size={15} />
                      </button>
                      <button
                        className="btn-ghost px-2 py-1 text-danger-500"
                        title="Excluir"
                        onClick={() => excluir(d)}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        open={modal}
        onClose={() => {
          if (!enviando) setModal(false);
        }}
        title="Enviar documentos"
      >
        <div className="space-y-4">
          <div>
            <label className="label">
              Arquivos * (pdf, docx, jpg, png, xlsx, xml — máx 50MB cada)
            </label>
            <div
              role="button"
              tabIndex={0}
              onClick={() => fileRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") fileRef.current?.click();
              }}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                adicionarArquivos(e.dataTransfer.files);
              }}
              className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed px-4 py-6 text-center text-sm transition-colors ${
                dragOver
                  ? "border-primary-400 bg-primary-50/60 dark:bg-primary-900/20"
                  : "border-slate-300 text-slate-500 hover:border-primary-300 dark:border-slate-600"
              }`}
            >
              <Upload size={20} className="text-slate-400" />
              <span>
                Arraste arquivos aqui ou{" "}
                <span className="font-medium text-primary-600">
                  clique para selecionar
                </span>
              </span>
              <span className="text-xs text-slate-400">
                Vários arquivos de uma vez — um envio por arquivo
              </span>
            </div>
            <input
              ref={fileRef}
              type="file"
              multiple
              className="hidden"
              accept={EXTS_UPLOAD.join(",")}
              onChange={(e) => {
                adicionarArquivos(e.target.files);
                e.target.value = "";
              }}
            />
          </div>

          {pendentes.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs uppercase text-slate-400">
                {pendentes.length} arquivo(s) na fila — título editável
              </div>
              {pendentes.map((p, i) => (
                <div
                  key={`${p.file.name}-${i}`}
                  className="rounded-lg border border-slate-200 p-2 dark:border-slate-700"
                >
                  <div className="flex items-center gap-2">
                    <input
                      className="input flex-1 py-1 text-sm"
                      value={p.titulo}
                      placeholder="Título do documento"
                      onChange={(e) =>
                        setPendentes((prev) =>
                          prev.map((x, j) =>
                            j === i ? { ...x, titulo: e.target.value } : x,
                          ),
                        )
                      }
                    />
                    <span className="shrink-0 text-xs text-slate-400">
                      {fmtKB(p.file.size)}
                    </span>
                    <button
                      className="btn-ghost shrink-0 px-1.5 py-1"
                      title="Remover da fila"
                      disabled={enviando}
                      onClick={() =>
                        setPendentes((prev) => prev.filter((_, j) => j !== i))
                      }
                    >
                      <X size={14} />
                    </button>
                  </div>
                  <div className="mt-0.5 truncate text-xs text-slate-400">
                    {p.file.name}
                  </div>
                  {p.erro && (
                    <div className="mt-1 text-xs text-danger-500">
                      Falhou: {p.erro}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          <div>
            <label className="label">Vincular ao caso (recomendado)</label>
            <select
              className="input"
              value={form.case_id || ""}
              onChange={(e) =>
                setForm({ ...form, case_id: e.target.value || undefined })
              }
            >
              <option value="">— Sem vínculo —</option>
              {casos.map((c) => (
                <option key={c.id} value={c.id}>
                  {(c.numero_interno ? c.numero_interno + " — " : "") +
                    (c.titulo || "Caso")}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-slate-400">
              Vincular a um caso controla quem pode acessar o documento (sigilo
              do cliente). Vale para todos os arquivos da fila.
            </p>
          </div>
          <div>
            <label className="label">Confidencialidade</label>
            <select
              className="input"
              value={form.confidencialidade}
              onChange={(e) =>
                setForm({ ...form, confidencialidade: e.target.value })
              }
            >
              <option value="normal">Normal</option>
              <option value="interno">Interno</option>
              <option value="restrito">Restrito (cofre — sócios)</option>
              <option value="confidencial">Confidencial (cofre)</option>
              <option value="segredo_justica">
                Segredo de justiça (cofre)
              </option>
            </select>
          </div>
          <button
            className="btn-primary w-full justify-center"
            disabled={enviando || pendentes.length === 0}
            onClick={upload}
          >
            {enviando
              ? progresso
                ? `Enviando ${progresso.done + 1}/${progresso.total}…`
                : "Enviando..."
              : pendentes.length > 1
                ? `Enviar ${pendentes.length} arquivos`
                : "Enviar"}
          </button>
        </div>
      </Modal>

      <Modal
        open={!!preview}
        onClose={fecharPreview}
        title={preview ? `Pré-visualização — ${preview.doc.titulo}` : ""}
        footer={
          preview ? (
            <>
              <button className="btn-ghost" onClick={fecharPreview}>
                Fechar
              </button>
              <button
                className="btn-primary"
                onClick={() => baixar(preview.doc)}
              >
                <Download size={14} /> Baixar
              </button>
            </>
          ) : undefined
        }
      >
        {preview && (
          <div className="min-h-[200px]">
            {previewErro ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                {previewErro}
              </div>
            ) : !previewUrl ? (
              <div className="py-8">
                <Spinner />
                <p className="mt-3 text-center text-xs text-slate-400">
                  Carregando o arquivo…
                </p>
              </div>
            ) : preview.kind === "pdf" ? (
              <iframe
                src={previewUrl}
                title={preview.doc.titulo}
                className="h-[70vh] w-full rounded-lg border border-slate-200 dark:border-slate-700"
              />
            ) : (
              <img
                src={previewUrl}
                alt={preview.doc.titulo}
                className="mx-auto max-h-[70vh] max-w-full rounded-lg object-contain"
              />
            )}
          </div>
        )}
      </Modal>

      <Modal
        open={!!classDoc}
        onClose={fecharClass}
        title="Classificar tipo (IA)"
        footer={
          classResult && classResult.disponivel && classResult.tipo_sugerido ? (
            <>
              <button className="btn-ghost" onClick={fecharClass}>
                Cancelar
              </button>
              <button
                className="btn-primary"
                disabled={aplicando}
                onClick={aplicarTipo}
              >
                {aplicando ? "Aplicando..." : "Aplicar tipo sugerido"}
              </button>
            </>
          ) : (
            <button className="btn-ghost" onClick={fecharClass}>
              Fechar
            </button>
          )
        }
      >
        {classDoc && (
          <p className="mb-4 text-sm text-slate-500">
            Documento:{" "}
            <span className="font-medium text-navy">{classDoc.titulo}</span>
          </p>
        )}

        {classLoading || !classResult ? (
          <div className="py-8">
            <Spinner />
            <p className="mt-3 text-center text-xs text-slate-400">
              Analisando o texto do documento…
            </p>
          </div>
        ) : !classResult.disponivel || !classResult.tipo_sugerido ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            Classificação por IA indisponível.
            {classResult.justificativa && (
              <span className="mt-1 block text-xs text-amber-700">
                {classResult.justificativa}
              </span>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-xl bg-slate-900/[0.04] p-4 dark:bg-white/[0.06]">
              <div className="text-xs uppercase text-slate-400">
                Tipo sugerido
              </div>
              <div className="mt-1 flex items-center gap-2">
                <span className="text-lg font-semibold capitalize text-navy">
                  {String(classResult.tipo_sugerido).replace(/_/g, " ")}
                </span>
                {classResult.confianca && (
                  <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600">
                    {CONF_LABEL[classResult.confianca] ?? classResult.confianca}
                  </span>
                )}
              </div>
              {classResult.tipo_atual && (
                <div className="mt-1 text-xs text-slate-400">
                  Tipo atual:{" "}
                  <span className="capitalize">
                    {String(classResult.tipo_atual).replace(/_/g, " ")}
                  </span>
                </div>
              )}
            </div>

            {classResult.justificativa && (
              <div>
                <div className="mb-1 text-xs uppercase text-slate-400">
                  Justificativa
                </div>
                <p className="text-sm text-slate-600">
                  {classResult.justificativa}
                </p>
              </div>
            )}

            {classResult.alternativas.length > 0 && (
              <div>
                <div className="mb-1 text-xs uppercase text-slate-400">
                  Alternativas
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {classResult.alternativas.map((a) => (
                    <span
                      key={a.tipo_key}
                      className="rounded-full bg-slate-900/[0.05] px-2.5 py-0.5 text-xs text-slate-600 dark:bg-white/[0.07] dark:text-slate-300"
                      title={a.tipo_key}
                    >
                      {a.nome}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <p className="text-xs text-slate-400">
              {classResult.aviso ||
                "Sugestão gerada por IA — confirmação humana obrigatória."}
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
}
