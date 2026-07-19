import { useEffect, useState, useRef } from "react";
import { toast } from "../components/Toast";
import {
  Upload,
  Download,
  Search,
  Link2,
  Lock,
  Pencil,
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

// Espelho de DocConfidencialidade do backend (mesmos valores do upload).
const CONF_OPCOES: { k: string; l: string }[] = [
  { k: "normal", l: "Normal" },
  { k: "interno", l: "Interno" },
  { k: "restrito", l: "Restrito (cofre — sócios)" },
  { k: "confidencial", l: "Confidencial (cofre)" },
  { k: "segredo_justica", l: "Segredo de justiça (cofre)" },
];

// Espelho de TIPOS_LEGADOS do backend: aceitos no PATCH além do master.
const TIPOS_LEGADOS = [
  "procuracao",
  "contrato",
  "decisao",
  "peticao",
  "prova",
  "outro",
];

/** Item de GET /documents/tipos (master de tipos ativos). */
type TipoDoc = { tipo_key: string; nome: string };

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

  // Filtros novos do GET /documents/ (tipo, confidencialidade, datas,
  // classificação pendente) — todos aditivos no backend.
  const [tipos, setTipos] = useState<TipoDoc[]>([]);
  const [tipoFiltro, setTipoFiltro] = useState("");
  const [confFiltro, setConfFiltro] = useState("");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [soPendentes, setSoPendentes] = useState(false);

  // Edição de metadados por linha (PATCH /documents/{id}).
  const [editDoc, setEditDoc] = useState<any | null>(null);
  const [editForm, setEditForm] = useState<any>({});
  const [salvandoEdit, setSalvandoEdit] = useState(false);

  // Ações em lote via PATCH (mesmo padrão sequencial do baixar/excluir).
  const [loteConfModal, setLoteConfModal] = useState(false);
  const [loteConf, setLoteConf] = useState("normal");
  const [loteCasoModal, setLoteCasoModal] = useState(false);
  const [loteCaso, setLoteCaso] = useState("");

  // Pré-visualização sem download (blob de GET /{id}/download).
  const [preview, setPreview] = useState<{
    doc: any;
    kind: "pdf" | "img";
  } | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewErro, setPreviewErro] = useState<string | null>(null);
  // Espelho da object URL ativa p/ revogá-la no unmount (evita vazamento de blob
  // quando o usuário navega com o preview aberto, sem passar por fecharPreview).
  const previewUrlRef = useRef<string | null>(null);
  previewUrlRef.current = previewUrl;
  useEffect(
    () => () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    },
    [],
  );

  // Seleção múltipla para ações em lote (baixar / excluir em sequência).
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [loteBusy, setLoteBusy] = useState<
    "download" | "delete" | "conf" | "vincular" | null
  >(null);

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
          tipo: tipoFiltro || undefined,
          confidencialidade: confFiltro || undefined,
          data_inicio: dataInicio || undefined,
          data_fim: dataFim || undefined,
          // Só envia quando marcado — false filtraria "somente classificados".
          classificacao_pendente: soPendentes || undefined,
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
    // Tipos do master (mesma fonte da validação do PATCH) + legados, para o
    // filtro por tipo e para o modal de edição.
    api
      .get("/documents/tipos")
      .then((r) => {
        const master: TipoDoc[] = Array.isArray(r.data?.data)
          ? r.data.data
          : [];
        const chaves = new Set(master.map((t) => t.tipo_key));
        setTipos([
          ...master,
          ...TIPOS_LEGADOS.filter((k) => !chaves.has(k)).map((k) => ({
            tipo_key: k,
            nome: k.replace(/_/g, " "),
          })),
        ]);
      })
      .catch(() => {
        // Fallback aos legados: filtro/edição continuam utilizáveis.
        setTipos(
          TIPOS_LEGADOS.map((k) => ({
            tipo_key: k,
            nome: k.replace(/_/g, " "),
          })),
        );
        toast.error("Falha ao carregar os tipos de documento");
      });
  }, []);
  useEffect(() => {
    const t = setTimeout(load, 350);
    return () => clearTimeout(t);
  }, [
    search,
    casoFiltro,
    clienteFiltro,
    tipoFiltro,
    confFiltro,
    dataInicio,
    dataFim,
    soPendentes,
  ]);

  // ── Upload múltiplo ────────────────────────────────────────────────────────
  const adicionarArquivos = (lista: FileList | File[] | null) => {
    if (!lista) return;
    const novos: PendenteUpload[] = [];
    const ignorados: string[] = [];
    Array.from(lista).forEach((f) => {
      if (!EXTS_UPLOAD.includes(extDe(f.name))) {
        ignorados.push(f.name);
        return;
      }
      // Título automático: nome do arquivo sem a extensão (editável abaixo).
      novos.push({ file: f, titulo: semExtensao(f.name) });
    });
    if (ignorados.length > 0) {
      // Mensagem completa: QUAIS arquivos foram recusados e QUAIS formatos
      // servem — a versão antiga ("extensão não permitida") não dizia nem
      // o arquivo nem a solução (usabilidade §3.5).
      const formatos = EXTS_UPLOAD.map((e) =>
        e.replace(".", "").toUpperCase(),
      ).join(", ");
      toast.error(
        ignorados.length === 1
          ? `O arquivo "${ignorados[0]}" não foi aceito. Formatos permitidos: ${formatos}.`
          : `Os arquivos ${ignorados.map((n) => `"${n}"`).join(", ")} não foram aceitos. Formatos permitidos: ${formatos}.`,
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
      !window.confirm(`Excluir ${selDocs.length} documento(s) selecionado(s)?`)
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

  // ── Edição de metadados (PATCH /documents/{id}) ───────────────────────────
  const patchErroMsg = (e: any) => {
    const st = e.response?.status;
    return (
      e.response?.data?.detail ||
      (st === 403
        ? "Sem permissão: mover para o cofre (restrito+) é restrito a sócios."
        : st === 400
          ? "Vínculo negado: o caso pertence a outro cliente."
          : "Falha ao atualizar o documento")
    );
  };

  const abrirEdicao = (d: any) => {
    setEditDoc(d);
    setEditForm({
      titulo: d.titulo || "",
      tipo: d.tipo || "",
      confidencialidade: d.confidencialidade,
      case_id: d.case_id || "",
    });
  };

  // Aplica na linha da lista os metadados retornados pelo PATCH.
  const aplicarPatchNaLista = (docId: string, r: any) =>
    setData((prev: any) =>
      prev
        ? {
            ...prev,
            data: (Array.isArray(prev.data) ? prev.data : []).map((x: any) =>
              x.id === docId
                ? {
                    ...x,
                    titulo: r.titulo,
                    tipo: r.tipo,
                    confidencialidade: r.confidencialidade,
                    case_id: r.case_id,
                  }
                : x,
            ),
          }
        : prev,
    );

  const salvarEdicao = async () => {
    if (!editDoc) return;
    if (!String(editForm.titulo || "").trim()) {
      toast.error("Título não pode ser vazio");
      return;
    }
    // Envia apenas o que mudou (PATCH parcial).
    const payload: Record<string, unknown> = {};
    if (editForm.titulo.trim() !== editDoc.titulo)
      payload.titulo = editForm.titulo.trim();
    if ((editForm.tipo || null) !== (editDoc.tipo || null))
      payload.tipo = editForm.tipo || null;
    if (editForm.confidencialidade !== editDoc.confidencialidade)
      payload.confidencialidade = editForm.confidencialidade;
    if ((editForm.case_id || null) !== (editDoc.case_id || null))
      payload.case_id = editForm.case_id || null;
    if (Object.keys(payload).length === 0) {
      toast.info("Nenhuma alteração para salvar");
      setEditDoc(null);
      return;
    }
    setSalvandoEdit(true);
    try {
      const r = await api.patch(`/documents/${editDoc.id}`, payload);
      aplicarPatchNaLista(editDoc.id, r.data);
      toast.success("Metadados atualizados");
      setEditDoc(null);
    } catch (e: any) {
      toast.error(patchErroMsg(e));
    } finally {
      setSalvandoEdit(false);
    }
  };

  // ── Lote via PATCH: alterar confidencialidade / vincular ao caso ──────────
  // Mesmo padrão do baixar/excluir em lote: sequencial, resumo de falhas por
  // título. Erros individuais não interrompem os demais itens.
  const patchLote = async (
    payload: Record<string, unknown>,
    acao: "conf" | "vincular",
  ) => {
    if (selDocs.length === 0) return;
    setLoteBusy(acao);
    let ok = 0;
    const falhas: string[] = [];
    let ultimoErro = "";
    for (const d of selDocs) {
      try {
        await api.patch(`/documents/${d.id}`, payload);
        ok += 1;
      } catch (e: any) {
        falhas.push(d.titulo);
        ultimoErro = patchErroMsg(e);
      }
    }
    setLoteBusy(null);
    setLoteConfModal(false);
    setLoteCasoModal(false);
    load();
    if (falhas.length === 0) {
      toast.success(`${ok} documento(s) atualizado(s)`);
    } else {
      toast.error(
        `${ok} atualizado(s), ${falhas.length} falhou(aram): ${falhas
          .slice(0, 3)
          .join(", ")}${falhas.length > 3 ? "…" : ""} — ${ultimoErro}`,
      );
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
        <select
          className="input w-auto max-w-[200px] text-sm"
          value={tipoFiltro}
          onChange={(e) => setTipoFiltro(e.target.value)}
          title="Filtrar por tipo"
        >
          <option value="">Todos os tipos</option>
          {tipos.map((t) => (
            <option key={t.tipo_key} value={t.tipo_key}>
              {t.nome}
            </option>
          ))}
        </select>
        <select
          className="input w-auto max-w-[220px] text-sm"
          value={confFiltro}
          onChange={(e) => setConfFiltro(e.target.value)}
          title="Filtrar por confidencialidade"
        >
          <option value="">Qualquer confidencialidade</option>
          {CONF_OPCOES.map((c) => (
            <option key={c.k} value={c.k}>
              {c.l}
            </option>
          ))}
        </select>
        <div
          className="flex items-center gap-1 text-xs text-slate-500"
          title="Filtrar por período de envio"
        >
          <input
            type="date"
            className="input w-auto py-1.5 text-sm"
            value={dataInicio}
            aria-label="Enviado a partir de"
            onChange={(e) => setDataInicio(e.target.value)}
          />
          <span>até</span>
          <input
            type="date"
            className="input w-auto py-1.5 text-sm"
            value={dataFim}
            aria-label="Enviado até"
            onChange={(e) => setDataFim(e.target.value)}
          />
        </div>
        <label className="flex cursor-pointer items-center gap-1.5 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={soPendentes}
            onChange={(e) => setSoPendentes(e.target.checked)}
          />
          Só classificação pendente
        </label>
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
            className="btn-ghost px-2 py-1"
            disabled={loteBusy !== null}
            onClick={() => {
              setLoteConf("normal");
              setLoteConfModal(true);
            }}
          >
            <Lock size={14} />
            {loteBusy === "conf" ? "Alterando…" : "Alterar confidencialidade"}
          </button>
          <button
            className="btn-ghost px-2 py-1"
            disabled={loteBusy !== null}
            onClick={() => {
              setLoteCaso("");
              setLoteCasoModal(true);
            }}
          >
            <Link2 size={14} />
            {loteBusy === "vincular" ? "Vinculando…" : "Vincular ao caso"}
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
                        title="Editar metadados"
                        onClick={() => abrirEdicao(d)}
                      >
                        <Pencil size={15} />
                      </button>
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
                if (e.key === "Enter" || e.key === " ")
                  fileRef.current?.click();
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

      {/* Edição de metadados por linha — PATCH /documents/{id} */}
      <Modal
        open={!!editDoc}
        onClose={() => {
          if (!salvandoEdit) setEditDoc(null);
        }}
        title="Editar documento"
        footer={
          <>
            <button
              className="btn-ghost"
              disabled={salvandoEdit}
              onClick={() => setEditDoc(null)}
            >
              Cancelar
            </button>
            <button
              className="btn-primary"
              disabled={salvandoEdit}
              onClick={salvarEdicao}
            >
              {salvandoEdit ? "Salvando..." : "Salvar"}
            </button>
          </>
        }
      >
        {editDoc && (
          <div className="space-y-4">
            <div>
              <label className="label">Título *</label>
              <input
                className="input"
                value={editForm.titulo || ""}
                onChange={(e) =>
                  setEditForm({ ...editForm, titulo: e.target.value })
                }
              />
            </div>
            <div>
              <label className="label">Tipo</label>
              <select
                className="input"
                value={editForm.tipo || ""}
                onChange={(e) =>
                  setEditForm({ ...editForm, tipo: e.target.value })
                }
              >
                <option value="">— Sem tipo (classificação pendente) —</option>
                {tipos.map((t) => (
                  <option key={t.tipo_key} value={t.tipo_key}>
                    {t.nome}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Confidencialidade</label>
              <select
                className="input"
                value={editForm.confidencialidade || "normal"}
                onChange={(e) =>
                  setEditForm({
                    ...editForm,
                    confidencialidade: e.target.value,
                  })
                }
              >
                {CONF_OPCOES.map((c) => (
                  <option key={c.k} value={c.k}>
                    {c.l}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-slate-400">
                Mover para restrito+ (cofre) exige perfil de sócio.
              </p>
            </div>
            <div>
              <label className="label">Caso vinculado</label>
              <select
                className="input"
                value={editForm.case_id || ""}
                onChange={(e) =>
                  setEditForm({ ...editForm, case_id: e.target.value })
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
                Documento de um cliente só pode apontar para caso do mesmo
                cliente.
              </p>
            </div>
          </div>
        )}
      </Modal>

      {/* Lote: alterar confidencialidade */}
      <Modal
        open={loteConfModal}
        onClose={() => {
          if (loteBusy === null) setLoteConfModal(false);
        }}
        title={`Alterar confidencialidade — ${selDocs.length} documento(s)`}
        footer={
          <>
            <button
              className="btn-ghost"
              disabled={loteBusy !== null}
              onClick={() => setLoteConfModal(false)}
            >
              Cancelar
            </button>
            <button
              className="btn-primary"
              disabled={loteBusy !== null}
              onClick={() => patchLote({ confidencialidade: loteConf }, "conf")}
            >
              {loteBusy === "conf" ? "Aplicando..." : "Aplicar a todos"}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="label">Novo nível</label>
            <select
              className="input"
              value={loteConf}
              onChange={(e) => setLoteConf(e.target.value)}
            >
              {CONF_OPCOES.map((c) => (
                <option key={c.k} value={c.k}>
                  {c.l}
                </option>
              ))}
            </select>
          </div>
          <p className="text-xs text-slate-400">
            Aplicado item a item — mover para restrito+ (cofre) exige perfil de
            sócio; falhas individuais aparecem no resumo.
          </p>
        </div>
      </Modal>

      {/* Lote: vincular ao caso */}
      <Modal
        open={loteCasoModal}
        onClose={() => {
          if (loteBusy === null) setLoteCasoModal(false);
        }}
        title={`Vincular ao caso — ${selDocs.length} documento(s)`}
        footer={
          <>
            <button
              className="btn-ghost"
              disabled={loteBusy !== null}
              onClick={() => setLoteCasoModal(false)}
            >
              Cancelar
            </button>
            <button
              className="btn-primary"
              disabled={loteBusy !== null || !loteCaso}
              onClick={() => patchLote({ case_id: loteCaso }, "vincular")}
            >
              {loteBusy === "vincular" ? "Vinculando..." : "Vincular todos"}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="label">Caso de destino</label>
            <select
              className="input"
              value={loteCaso}
              onChange={(e) => setLoteCaso(e.target.value)}
            >
              <option value="">Selecione...</option>
              {casos.map((c) => (
                <option key={c.id} value={c.id}>
                  {(c.numero_interno ? c.numero_interno + " — " : "") +
                    (c.titulo || "Caso")}
                </option>
              ))}
            </select>
          </div>
          <p className="text-xs text-slate-400">
            Documento de um cliente só pode apontar para caso do mesmo cliente
            (itens de outros clientes falham no resumo, sem afetar os demais).
          </p>
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
