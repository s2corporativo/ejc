import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  Filter,
  FolderInput,
  Inbox,
  Link2,
  MoreHorizontal,
  Search,
  ShieldCheck,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "../components/Toast";
import { Button, Modal, Spinner } from "../components/UI";
import CaseFilterChip from "../components/CaseFilterChip";
import DocumentDrawer from "../components/documents/DocumentDrawer";
import DocumentStatusBadge from "../components/documents/DocumentStatusBadge";
import DocumentWorkflowStats from "../components/documents/DocumentWorkflowStats";
import { useCasoFiltro } from "../contexts/useCasoFiltro";
import { asList } from "../lib/list";
import { useAuth } from "../stores/auth";
import {
  ATTENTION_LABEL,
  duplicateDetail,
  getDocumentBlob,
  getDocumentPolicy,
  listDocuments,
  listInbox,
  moveDocumentToTrash,
  updateDocumentMetadata,
  uploadDocument,
  type DocumentItem,
  type DocumentListResponse,
  type DocumentPolicy,
} from "../services/documents";

type ViewMode = "inbox" | "all" | "recent";
type TipoDoc = { tipo_key: string; nome: string };
type CasoResumo = { id: string; titulo?: string; client_id?: string | null };
type ClienteResumo = { id: string; nome?: string; razao_social?: string };
type PendingUpload = { file: File; titulo: string; erro?: string };

const SOCIO_PLUS = new Set(["superadmin", "admin", "socio"]);
const CAN_LINK = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "advogado_auxiliar",
  "estagiario",
]);
const LEGACY_TYPES = ["procuracao", "contrato", "decisao", "peticao", "prova", "outro"];
const PREVIEW_EXT = new Set([".pdf", ".jpg", ".jpeg", ".png"]);

const extOf = (name?: string | null) => {
  const value = name || "";
  const index = value.lastIndexOf(".");
  return index >= 0 ? value.slice(index).toLowerCase() : "";
};

const withoutExt = (name: string) => {
  const index = name.lastIndexOf(".");
  return index > 0 ? name.slice(0, index) : name;
};

const fmtDate = (value?: string | null) =>
  value
    ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" }).format(new Date(value))
    : "—";

const fmtBytes = (value?: number | null) => {
  if (!value) return "—";
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
};

const confLabel = (value?: string | null) =>
  ({
    normal: "Normal",
    interno: "Interno",
    restrito: "Restrito",
    confidencial: "Confidencial",
    segredo_justica: "Segredo de justiça",
  })[value || ""] || value || "—";

const roleCanUseConf = (role: string, conf: string) =>
  SOCIO_PLUS.has(role) || !["restrito", "confidencial", "segredo_justica"].includes(conf);

function recentStartDate(): string {
  const date = new Date();
  date.setDate(date.getDate() - 30);
  return date.toISOString().slice(0, 10);
}

export default function Documentos() {
  const navigate = useNavigate();
  const user = useAuth((state) => state.user);
  const role = user?.role || "";
  const canLink = CAN_LINK.has(role);
  const { casoFiltro, casoFiltroNome, removerFiltro } = useCasoFiltro();

  const [mode, setMode] = useState<ViewMode>("inbox");
  const [response, setResponse] = useState<DocumentListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [search, setSearch] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [clientId, setClientId] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [confFilter, setConfFilter] = useState("");
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");
  const [pendingClassification, setPendingClassification] = useState(false);
  const [policy, setPolicy] = useState<DocumentPolicy | null>(null);
  const [types, setTypes] = useState<TipoDoc[]>([]);
  const [cases, setCases] = useState<CasoResumo[]>([]);
  const [clients, setClients] = useState<ClienteResumo[]>([]);
  const [drawerId, setDrawerId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [menuId, setMenuId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const seq = useRef(0);

  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploads, setUploads] = useState<PendingUpload[]>([]);
  const [uploadType, setUploadType] = useState("");
  const [uploadConf, setUploadConf] = useState("normal");
  const [uploadCaseId, setUploadCaseId] = useState("");
  const [uploadClientId, setUploadClientId] = useState("");
  const [predecessor, setPredecessor] = useState<DocumentItem | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ done: number; total: number } | null>(null);

  const [editDoc, setEditDoc] = useState<DocumentItem | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editType, setEditType] = useState("");
  const [editConf, setEditConf] = useState("normal");
  const [editBusy, setEditBusy] = useState(false);

  const [linkOpen, setLinkOpen] = useState(false);
  const [linkCaseId, setLinkCaseId] = useState("");
  const [batchBusy, setBatchBusy] = useState<"download" | "delete" | "link" | "conf" | null>(null);
  const [batchConfOpen, setBatchConfOpen] = useState(false);
  const [batchConf, setBatchConf] = useState("normal");

  const docs = response?.data || [];
  const total = response?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const selectedDocs = useMemo(
    () => docs.filter((doc) => selected.has(doc.id)),
    [docs, selected],
  );

  const load = async () => {
    const requestId = ++seq.current;
    setLoading(true);
    setLoadError(false);
    try {
      let result: DocumentListResponse;
      if (mode === "inbox") {
        result = await listInbox({
          page,
          pageSize,
          caseId: casoFiltro,
          clientId: clientId || undefined,
        });
      } else {
        result = await listDocuments({
          page,
          pageSize,
          search: search || undefined,
          caseId: casoFiltro,
          clientId: clientId || undefined,
          tipo: typeFilter || undefined,
          confidencialidade: confFilter || undefined,
          dataInicio: mode === "recent" ? recentStartDate() : dateStart || undefined,
          dataFim: dateEnd || undefined,
          classificacaoPendente: pendingClassification || undefined,
        });
      }
      if (requestId !== seq.current) return;
      setResponse(result);
      setSelected(new Set());
    } catch {
      if (requestId !== seq.current) return;
      setLoadError(true);
      setResponse(null);
    } finally {
      if (requestId === seq.current) setLoading(false);
    }
  };

  useEffect(() => {
    void Promise.all([
      getDocumentPolicy().then(setPolicy).catch(() => setPolicy(null)),
      api
        .get("/documents/tipos")
        .then((res) => {
          const master: TipoDoc[] = Array.isArray(res.data?.data) ? res.data.data : [];
          const keys = new Set(master.map((item) => item.tipo_key));
          setTypes([
            ...master,
            ...LEGACY_TYPES.filter((key) => !keys.has(key)).map((key) => ({
              tipo_key: key,
              nome: key.replaceAll("_", " "),
            })),
          ]);
        })
        .catch(() =>
          setTypes(LEGACY_TYPES.map((key) => ({ tipo_key: key, nome: key.replaceAll("_", " ") }))),
        ),
      api
        .get("/cases/", { params: { page_size: 100 } })
        .then((res) => setCases(asList(res.data) as CasoResumo[]))
        .catch(() => setCases([])),
      api
        .get("/clients/", { params: { page_size: 100 } })
        .then((res) => setClients(asList(res.data) as ClienteResumo[]))
        .catch(() => setClients([])),
    ]);
  }, []);

  useEffect(() => {
    setPage(1);
  }, [mode, search, casoFiltro, clientId, typeFilter, confFilter, dateStart, dateEnd, pendingClassification]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), mode === "inbox" ? 0 : 300);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, page, search, casoFiltro, clientId, typeFilter, confFilter, dateStart, dateEnd, pendingClassification, refreshKey]);

  const changed = () => {
    setRefreshKey((value) => value + 1);
    void load();
  };

  const resetUpload = () => {
    setUploads([]);
    setUploadType("");
    setUploadConf("normal");
    setUploadCaseId(casoFiltro || "");
    setUploadClientId("");
    setPredecessor(null);
    setUploadProgress(null);
  };

  const openUpload = (previous?: DocumentItem) => {
    resetUpload();
    if (previous) {
      setPredecessor(previous);
      setUploadType(previous.tipo || "");
      setUploadConf(previous.confidencialidade || "normal");
      setUploadCaseId(previous.case_id || "");
      setUploadClientId(previous.client_id || "");
    } else if (casoFiltro) {
      setUploadCaseId(casoFiltro);
    }
    setUploadOpen(true);
  };

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const allowed = new Set((policy?.extensions || []).map((item) => item.toLowerCase()));
    const maxBytes = (policy?.max_upload_mb || 0) * 1024 * 1024;
    const added: PendingUpload[] = [];
    for (const file of Array.from(files)) {
      const ext = extOf(file.name);
      if (allowed.size > 0 && !allowed.has(ext)) {
        toast.error(`Formato não permitido: ${file.name}`);
        continue;
      }
      if (maxBytes > 0 && file.size > maxBytes) {
        toast.error(`${file.name} excede ${policy?.max_upload_mb} MB`);
        continue;
      }
      added.push({ file, titulo: withoutExt(file.name) });
      if (predecessor) break;
    }
    setUploads((current) => (predecessor ? added.slice(0, 1) : [...current, ...added]));
  };

  const submitUpload = async () => {
    if (uploads.length === 0) {
      toast.error("Selecione ao menos um arquivo");
      return;
    }
    if (uploads.some((item) => !item.titulo.trim())) {
      toast.error("Todo documento precisa de um título");
      return;
    }
    setUploadBusy(true);
    const failed: PendingUpload[] = [];
    let success = 0;
    try {
      for (let index = 0; index < uploads.length; index += 1) {
        const item = uploads[index];
        setUploadProgress({ done: index, total: uploads.length });
        const selectedCase = cases.find((entry) => String(entry.id) === uploadCaseId);
        const inferredClient = uploadClientId || selectedCase?.client_id || undefined;
        const request = {
          file: item.file,
          titulo: item.titulo,
          tipo: uploadType || undefined,
          confidencialidade: uploadConf,
          caseId: uploadCaseId || undefined,
          clientId: inferredClient || undefined,
          predecessorId: predecessor?.id || undefined,
        };
        try {
          await uploadDocument(request);
          success += 1;
        } catch (error) {
          const duplicate = duplicateDetail(error);
          if (duplicate) {
            const proceed = window.confirm(
              "Já existe um arquivo idêntico neste contexto. Deseja registrar outra cópia mesmo assim? A decisão ficará auditada.",
            );
            if (proceed) {
              try {
                await uploadDocument({ ...request, allowDuplicate: true });
                success += 1;
                continue;
              } catch {
                // cai no registro de falha abaixo
              }
            }
          }
          failed.push({ ...item, erro: "Não foi possível enviar este documento" });
        }
      }
    } finally {
      setUploadBusy(false);
      setUploadProgress(null);
    }
    if (success > 0) changed();
    if (failed.length === 0) {
      toast.success(success === 1 ? "Documento enviado" : `${success} documentos enviados`);
      setUploadOpen(false);
      resetUpload();
    } else {
      setUploads(failed);
      toast.error(`${failed.length} documento(s) precisam ser reenviados`);
    }
  };

  const download = async (doc: DocumentItem) => {
    try {
      const blob = await getDocumentBlob(doc.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = doc.filename || doc.titulo;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Falha ao baixar o documento");
    }
  };

  const edit = (doc: DocumentItem) => {
    setEditDoc(doc);
    setEditTitle(doc.titulo || "");
    setEditType(doc.tipo || "");
    setEditConf(doc.confidencialidade || "normal");
    setMenuId(null);
  };

  const saveEdit = async () => {
    if (!editDoc || !editTitle.trim()) return;
    setEditBusy(true);
    try {
      await updateDocumentMetadata(editDoc.id, {
        titulo: editTitle.trim(),
        tipo: editType || null,
        confidencialidade: editConf,
      });
      toast.success("Documento atualizado");
      setEditDoc(null);
      changed();
    } catch {
      toast.error("Não foi possível atualizar o documento");
    } finally {
      setEditBusy(false);
    }
  };

  const removeOne = async (doc: DocumentItem) => {
    setMenuId(null);
    if (!window.confirm(`Mover “${doc.titulo}” para a Lixeira? O arquivo físico será preservado.`)) return;
    try {
      await moveDocumentToTrash(doc.id);
      toast.success("Documento movido para a Lixeira");
      if (drawerId === doc.id) setDrawerId(null);
      changed();
    } catch {
      toast.error("Não foi possível mover o documento para a Lixeira");
    }
  };

  const batchDownload = async () => {
    if (!selectedDocs.length) return;
    setBatchBusy("download");
    try {
      for (const doc of selectedDocs) await download(doc);
    } finally {
      setBatchBusy(null);
    }
  };

  const batchDelete = async () => {
    if (!selectedDocs.length) return;
    if (!window.confirm(`Mover ${selectedDocs.length} documento(s) para a Lixeira?`)) return;
    setBatchBusy("delete");
    let failures = 0;
    for (const doc of selectedDocs) {
      try {
        await moveDocumentToTrash(doc.id);
      } catch {
        failures += 1;
      }
    }
    setBatchBusy(null);
    toast[failures ? "error" : "success"](
      failures ? `${failures} documento(s) não puderam ser removidos` : "Documentos movidos para a Lixeira",
    );
    changed();
  };

  const batchLink = async () => {
    if (!selectedDocs.length || !linkCaseId) return;
    setBatchBusy("link");
    let failures = 0;
    for (const doc of selectedDocs) {
      try {
        await api.post(`/cases/${linkCaseId}/documentos/${doc.id}/vincular`);
      } catch {
        failures += 1;
      }
    }
    setBatchBusy(null);
    setLinkOpen(false);
    toast[failures ? "error" : "success"](
      failures ? `${failures} vínculo(s) não puderam ser concluídos` : "Documentos vinculados ao caso",
    );
    changed();
  };

  const batchSetConf = async () => {
    if (!selectedDocs.length) return;
    setBatchBusy("conf");
    let failures = 0;
    for (const doc of selectedDocs) {
      try {
        await updateDocumentMetadata(doc.id, { confidencialidade: batchConf });
      } catch {
        failures += 1;
      }
    }
    setBatchBusy(null);
    setBatchConfOpen(false);
    toast[failures ? "error" : "success"](
      failures ? `${failures} documento(s) não puderam ter o acesso alterado` : "Nível de acesso atualizado",
    );
    changed();
  };

  const toggleAll = (checked: boolean) =>
    setSelected(checked ? new Set(docs.map((doc) => doc.id)) : new Set());

  const toggleOne = (id: string, checked: boolean) =>
    setSelected((current) => {
      const next = new Set(current);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });

  const activeFilters = [clientId, typeFilter, confFilter, dateStart, dateEnd, pendingClassification ? "1" : ""].filter(Boolean).length;

  return (
    <div className="mx-auto w-full max-w-[1500px] space-y-5 px-4 pb-10 pt-4 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium text-slate-500">
            <FileText size={16} />
            Gestão documental
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">Documentos</h1>
          <p className="mt-1 max-w-3xl text-sm text-slate-500">
            Organize o acervo, trate pendências, envie novas versões e controle o uso dos documentos na inteligência jurídica.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" onClick={() => navigate("/lixeira")} icon={<Trash2 size={15} />}>
            Lixeira
          </Button>
          <Button onClick={() => openUpload()} icon={<Upload size={15} />}>
            Enviar documento
          </Button>
        </div>
      </div>

      {casoFiltro && (
        <CaseFilterChip
          casoId={casoFiltro}
          nome={casoFiltroNome}
          onRemove={removerFiltro}
        />
      )}

      <DocumentWorkflowStats refreshKey={refreshKey} />

      <section className="overflow-visible rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-white/[0.08] dark:bg-slate-950">
        <div className="border-b border-slate-100 px-4 pt-4 dark:border-white/[0.08] sm:px-5">
          <div className="flex flex-wrap items-center gap-1">
            {([
              ["inbox", "Entrada", Inbox],
              ["all", "Todos", FileText],
              ["recent", "Recentes", FolderInput],
            ] as const).map(([value, label, Icon]) => (
              <button
                key={value}
                type="button"
                onClick={() => setMode(value)}
                className={`inline-flex items-center gap-2 rounded-t-lg border-b-2 px-3 py-2 text-sm font-semibold transition ${
                  mode === value
                    ? "border-primary-600 text-primary-700"
                    : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                }`}
              >
                <Icon size={15} />
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-3 p-4 sm:p-5">
          {mode === "inbox" ? (
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Itens que precisam de ação</h2>
                <p className="mt-0.5 text-xs text-slate-500">
                  Documentos sem vínculo, sem classificação ou com processamento que exige revisão.
                </p>
              </div>
              <select
                value={clientId}
                onChange={(event) => setClientId(event.target.value)}
                className="input min-w-56"
                aria-label="Filtrar caixa de entrada por cliente"
              >
                <option value="">Todos os clientes</option>
                {clients.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.nome || client.razao_social || client.id}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <>
              <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
                <label className="relative flex-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
                  <input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Buscar por título ou conteúdo indexado"
                    className="input w-full pl-9"
                  />
                </label>
                <Button
                  variant="secondary"
                  onClick={() => setShowFilters((value) => !value)}
                  icon={<Filter size={15} />}
                >
                  Filtros{activeFilters ? ` (${activeFilters})` : ""}
                </Button>
              </div>

              {showFilters && (
                <div className="grid gap-3 rounded-xl bg-slate-50 p-4 dark:bg-white/[0.04] sm:grid-cols-2 xl:grid-cols-5">
                  <label className="space-y-1 text-xs font-medium text-slate-600">
                    Cliente
                    <select value={clientId} onChange={(event) => setClientId(event.target.value)} className="input w-full">
                      <option value="">Todos</option>
                      {clients.map((client) => (
                        <option key={client.id} value={client.id}>
                          {client.nome || client.razao_social || client.id}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="space-y-1 text-xs font-medium text-slate-600">
                    Tipo
                    <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} className="input w-full">
                      <option value="">Todos</option>
                      {types.map((item) => (
                        <option key={item.tipo_key} value={item.tipo_key}>{item.nome}</option>
                      ))}
                    </select>
                  </label>
                  <label className="space-y-1 text-xs font-medium text-slate-600">
                    Acesso
                    <select value={confFilter} onChange={(event) => setConfFilter(event.target.value)} className="input w-full">
                      <option value="">Todos</option>
                      {(policy?.confidentiality || ["normal", "interno", "restrito", "confidencial", "segredo_justica"]).map((value) => (
                        <option key={value} value={value}>{confLabel(value)}</option>
                      ))}
                    </select>
                  </label>
                  <label className="space-y-1 text-xs font-medium text-slate-600">
                    De
                    <input type="date" value={dateStart} onChange={(event) => setDateStart(event.target.value)} className="input w-full" disabled={mode === "recent"} />
                  </label>
                  <label className="space-y-1 text-xs font-medium text-slate-600">
                    Até
                    <input type="date" value={dateEnd} onChange={(event) => setDateEnd(event.target.value)} className="input w-full" />
                  </label>
                  <label className="flex items-center gap-2 text-xs font-medium text-slate-600 sm:col-span-2">
                    <input
                      type="checkbox"
                      checked={pendingClassification}
                      onChange={(event) => setPendingClassification(event.target.checked)}
                    />
                    Somente documentos com tipo pendente
                  </label>
                </div>
              )}
            </>
          )}

          {selectedDocs.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-primary-200 bg-primary-50/60 px-3 py-2 dark:border-primary-900/50 dark:bg-primary-950/20">
              <span className="mr-1 text-xs font-semibold text-primary-800 dark:text-primary-200">
                {selectedDocs.length} selecionado(s)
              </span>
              <Button size="sm" variant="secondary" disabled={batchBusy !== null} onClick={() => void batchDownload()} icon={<Download size={14} />}>
                Baixar
              </Button>
              {canLink && (
                <Button size="sm" variant="secondary" disabled={batchBusy !== null} onClick={() => setLinkOpen(true)} icon={<Link2 size={14} />}>
                  Vincular ao caso
                </Button>
              )}
              <Button size="sm" variant="secondary" disabled={batchBusy !== null} onClick={() => setBatchConfOpen(true)} icon={<ShieldCheck size={14} />}>
                Alterar acesso
              </Button>
              <Button size="sm" variant="ghost" disabled={batchBusy !== null} onClick={() => void batchDelete()} icon={<Trash2 size={14} />}>
                Lixeira
              </Button>
              <button type="button" onClick={() => setSelected(new Set())} className="ml-auto p-1 text-slate-400 hover:text-slate-700" aria-label="Limpar seleção">
                <X size={16} />
              </button>
            </div>
          )}

          {loading ? (
            <div className="grid min-h-64 place-items-center"><Spinner /></div>
          ) : loadError ? (
            <div className="rounded-xl border border-danger-200 bg-danger-50 p-6 text-center">
              <p className="text-sm font-semibold text-danger-800">Não foi possível carregar os documentos.</p>
              <Button className="mt-3" variant="secondary" onClick={() => void load()}>Tentar novamente</Button>
            </div>
          ) : docs.length === 0 ? (
            <div className="grid min-h-64 place-items-center rounded-xl border border-dashed border-slate-200 p-8 text-center dark:border-white/[0.1]">
              <div>
                <FileText className="mx-auto text-slate-300" size={32} />
                <p className="mt-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
                  {mode === "inbox" ? "Nenhuma pendência documental" : "Nenhum documento encontrado"}
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  {mode === "inbox" ? "Os itens que exigirem ação aparecerão aqui." : "Ajuste os filtros ou envie um novo documento."}
                </p>
              </div>
            </div>
          ) : (
            <div className="overflow-visible rounded-xl border border-slate-200 dark:border-white/[0.08]">
              <div className="overflow-x-auto overflow-y-visible">
                <table className="w-full min-w-[940px] text-left text-sm">
                  <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:bg-white/[0.04]">
                    <tr>
                      <th className="w-10 px-3 py-3">
                        <input
                          type="checkbox"
                          checked={docs.length > 0 && selected.size === docs.length}
                          onChange={(event) => toggleAll(event.target.checked)}
                          aria-label="Selecionar página"
                        />
                      </th>
                      <th className="px-3 py-3">Documento</th>
                      <th className="px-3 py-3">Tipo</th>
                      <th className="px-3 py-3">Acesso</th>
                      <th className="px-3 py-3">Status</th>
                      <th className="px-3 py-3">Versão</th>
                      <th className="px-3 py-3">Data</th>
                      <th className="w-12 px-3 py-3" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-white/[0.06]">
                    {docs.map((doc) => (
                      <tr key={doc.id} className="group hover:bg-slate-50/70 dark:hover:bg-white/[0.03]">
                        <td className="px-3 py-3 align-top">
                          <input
                            type="checkbox"
                            checked={selected.has(doc.id)}
                            onChange={(event) => toggleOne(doc.id, event.target.checked)}
                            aria-label={`Selecionar ${doc.titulo}`}
                          />
                        </td>
                        <td className="max-w-[420px] px-3 py-3 align-top">
                          <button type="button" onClick={() => setDrawerId(doc.id)} className="block max-w-full text-left">
                            <span className="block truncate font-semibold text-slate-900 hover:text-primary-700 dark:text-white">{doc.titulo}</span>
                            <span className="mt-0.5 block truncate text-xs text-slate-400">
                              {doc.filename} · {fmtBytes(doc.size_bytes)}
                            </span>
                            {mode === "inbox" && (doc.attention_reasons || []).length > 0 && (
                              <span className="mt-1 flex flex-wrap gap-1">
                                {(doc.attention_reasons || []).slice(0, 2).map((reason) => (
                                  <span key={reason} className="rounded bg-warn-50 px-1.5 py-0.5 text-[10px] font-medium text-warn-700">
                                    {ATTENTION_LABEL[reason] || "Precisa de ação"}
                                  </span>
                                ))}
                              </span>
                            )}
                          </button>
                        </td>
                        <td className="px-3 py-3 align-top capitalize text-slate-600 dark:text-slate-300">{doc.tipo?.replaceAll("_", " ") || "Não classificado"}</td>
                        <td className="px-3 py-3 align-top text-slate-600 dark:text-slate-300">{confLabel(doc.confidencialidade)}</td>
                        <td className="px-3 py-3 align-top"><DocumentStatusBadge document={doc} /></td>
                        <td className="px-3 py-3 align-top text-slate-500">v{doc.versao || 1}</td>
                        <td className="px-3 py-3 align-top text-slate-500">{fmtDate(doc.created_at)}</td>
                        <td className="relative px-3 py-3 align-top">
                          <button
                            type="button"
                            onClick={() => setMenuId((current) => (current === doc.id ? null : doc.id))}
                            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-white/[0.08]"
                            aria-label={`Ações de ${doc.titulo}`}
                          >
                            <MoreHorizontal size={17} />
                          </button>
                          {menuId === doc.id && (
                            <div className="absolute right-3 top-11 z-30 w-48 rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl dark:border-white/[0.1] dark:bg-slate-900">
                              <button type="button" onClick={() => { setDrawerId(doc.id); setMenuId(null); }} className="menu-item w-full">Abrir detalhes</button>
                              <button type="button" onClick={() => { void download(doc); setMenuId(null); }} className="menu-item w-full">Baixar</button>
                              <button type="button" onClick={() => edit(doc)} className="menu-item w-full">Editar metadados</button>
                              <button type="button" onClick={() => { openUpload(doc); setMenuId(null); }} className="menu-item w-full">Enviar nova versão</button>
                              <button type="button" onClick={() => void removeOne(doc)} className="menu-item w-full text-danger-600">Mover para Lixeira</button>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {!loading && !loadError && total > 0 && (
            <div className="flex flex-col gap-2 border-t border-slate-100 pt-3 text-xs text-slate-500 dark:border-white/[0.08] sm:flex-row sm:items-center sm:justify-between">
              <span>
                {total.toLocaleString("pt-BR")} documento(s) · página {Math.min(page, pageCount)} de {pageCount}
              </span>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} icon={<ChevronLeft size={14} />}>
                  Anterior
                </Button>
                <Button size="sm" variant="secondary" disabled={page >= pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))} icon={<ChevronRight size={14} />}>
                  Próxima
                </Button>
              </div>
            </div>
          )}
        </div>
      </section>

      <DocumentDrawer
        documentId={drawerId}
        onClose={() => setDrawerId(null)}
        onNewVersion={(doc) => openUpload(doc)}
        onChanged={changed}
      />

      <Modal
        open={uploadOpen}
        onClose={() => !uploadBusy && setUploadOpen(false)}
        title={predecessor ? `Nova versão — ${predecessor.titulo}` : "Enviar documento"}
        size="lg"
        footer={
          <>
            <Button variant="secondary" disabled={uploadBusy} onClick={() => setUploadOpen(false)}>Cancelar</Button>
            <Button disabled={uploadBusy || uploads.length === 0} onClick={() => void submitUpload()}>
              {uploadBusy ? "Enviando…" : predecessor ? "Enviar nova versão" : uploads.length > 1 ? `Enviar ${uploads.length} documentos` : "Enviar documento"}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {predecessor && (
            <div className="rounded-xl border border-info-200 bg-info-50 p-3 text-sm text-info-800">
              Esta operação criará uma nova versão ligada explicitamente à versão v{predecessor.versao || 1}. A versão anterior será preservada no histórico.
            </div>
          )}

          <label className="block rounded-xl border-2 border-dashed border-slate-200 p-5 text-center hover:border-primary-300">
            <Upload className="mx-auto text-slate-400" size={24} />
            <span className="mt-2 block text-sm font-semibold text-slate-700">Escolher {predecessor ? "arquivo" : "arquivos"}</span>
            <span className="mt-1 block text-xs text-slate-400">
              {(policy?.extensions || []).map((item) => item.replace(".", "").toUpperCase()).join(", ") || "Formatos definidos pelo servidor"}
              {policy?.max_upload_mb ? ` · até ${policy.max_upload_mb} MB por arquivo` : ""}
            </span>
            <input
              type="file"
              multiple={!predecessor}
              accept={(policy?.extensions || []).join(",") || undefined}
              onChange={(event) => addFiles(event.target.files)}
              className="hidden"
            />
          </label>

          {uploads.length > 0 && (
            <div className="space-y-2">
              {uploads.map((item, index) => (
                <div key={`${item.file.name}-${index}`} className="flex items-center gap-2 rounded-lg border border-slate-200 p-2">
                  <FileText size={16} className="shrink-0 text-slate-400" />
                  <input
                    value={item.titulo}
                    onChange={(event) =>
                      setUploads((current) => current.map((entry, entryIndex) => entryIndex === index ? { ...entry, titulo: event.target.value } : entry))
                    }
                    className="input min-w-0 flex-1"
                    aria-label={`Título de ${item.file.name}`}
                  />
                  <span className="hidden text-xs text-slate-400 sm:inline">{fmtBytes(item.file.size)}</span>
                  <button type="button" onClick={() => setUploads((current) => current.filter((_, entryIndex) => entryIndex !== index))} className="p-1 text-slate-400 hover:text-danger-600" aria-label="Remover arquivo">
                    <X size={15} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1 text-xs font-medium text-slate-600">
              Tipo
              <select value={uploadType} onChange={(event) => setUploadType(event.target.value)} className="input w-full">
                <option value="">Classificar depois</option>
                {types.map((item) => <option key={item.tipo_key} value={item.tipo_key}>{item.nome}</option>)}
              </select>
            </label>
            <label className="space-y-1 text-xs font-medium text-slate-600">
              Nível de acesso
              <select value={uploadConf} onChange={(event) => setUploadConf(event.target.value)} className="input w-full">
                {(policy?.confidentiality || ["normal", "interno", "restrito", "confidencial", "segredo_justica"])
                  .filter((value) => roleCanUseConf(role, value))
                  .map((value) => <option key={value} value={value}>{confLabel(value)}</option>)}
              </select>
            </label>
            <label className="space-y-1 text-xs font-medium text-slate-600">
              Caso
              <select value={uploadCaseId} onChange={(event) => setUploadCaseId(event.target.value)} className="input w-full" disabled={Boolean(predecessor?.case_id)}>
                <option value="">Sem caso por enquanto</option>
                {cases.map((item) => <option key={item.id} value={item.id}>{item.titulo || item.id}</option>)}
              </select>
            </label>
            <label className="space-y-1 text-xs font-medium text-slate-600">
              Cliente
              <select value={uploadClientId} onChange={(event) => setUploadClientId(event.target.value)} className="input w-full" disabled={Boolean(predecessor?.client_id)}>
                <option value="">Inferir pelo caso / não informado</option>
                {clients.map((item) => <option key={item.id} value={item.id}>{item.nome || item.razao_social || item.id}</option>)}
              </select>
            </label>
          </div>

          {uploadProgress && (
            <div className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
              Enviando {Math.min(uploadProgress.done + 1, uploadProgress.total)} de {uploadProgress.total}…
            </div>
          )}
        </div>
      </Modal>

      <Modal
        open={Boolean(editDoc)}
        onClose={() => !editBusy && setEditDoc(null)}
        title="Editar documento"
        footer={
          <>
            <Button variant="secondary" disabled={editBusy} onClick={() => setEditDoc(null)}>Cancelar</Button>
            <Button disabled={editBusy || !editTitle.trim()} onClick={() => void saveEdit()}>{editBusy ? "Salvando…" : "Salvar"}</Button>
          </>
        }
      >
        <div className="space-y-3">
          <label className="block space-y-1 text-xs font-medium text-slate-600">
            Título
            <input value={editTitle} onChange={(event) => setEditTitle(event.target.value)} className="input w-full" maxLength={255} />
          </label>
          <label className="block space-y-1 text-xs font-medium text-slate-600">
            Tipo
            <select value={editType} onChange={(event) => setEditType(event.target.value)} className="input w-full">
              <option value="">Não classificado</option>
              {types.map((item) => <option key={item.tipo_key} value={item.tipo_key}>{item.nome}</option>)}
            </select>
          </label>
          <label className="block space-y-1 text-xs font-medium text-slate-600">
            Nível de acesso
            <select value={editConf} onChange={(event) => setEditConf(event.target.value)} className="input w-full">
              {(policy?.confidentiality || ["normal", "interno", "restrito", "confidencial", "segredo_justica"])
                .filter((value) => roleCanUseConf(role, value))
                .map((value) => <option key={value} value={value}>{confLabel(value)}</option>)}
            </select>
          </label>
        </div>
      </Modal>

      <Modal
        open={linkOpen}
        onClose={() => !batchBusy && setLinkOpen(false)}
        title="Vincular documentos ao caso"
        footer={
          <>
            <Button variant="secondary" disabled={batchBusy !== null} onClick={() => setLinkOpen(false)}>Cancelar</Button>
            <Button disabled={!linkCaseId || batchBusy !== null} onClick={() => void batchLink()}>{batchBusy === "link" ? "Vinculando…" : "Vincular"}</Button>
          </>
        }
      >
        <p className="mb-3 text-sm text-slate-500">O vínculo é validado pelo backend e respeita cliente, caso e permissões do usuário.</p>
        <select value={linkCaseId} onChange={(event) => setLinkCaseId(event.target.value)} className="input w-full">
          <option value="">Selecione o caso</option>
          {cases.map((item) => <option key={item.id} value={item.id}>{item.titulo || item.id}</option>)}
        </select>
      </Modal>

      <Modal
        open={batchConfOpen}
        onClose={() => !batchBusy && setBatchConfOpen(false)}
        title="Alterar nível de acesso"
        footer={
          <>
            <Button variant="secondary" disabled={batchBusy !== null} onClick={() => setBatchConfOpen(false)}>Cancelar</Button>
            <Button disabled={batchBusy !== null} onClick={() => void batchSetConf()}>{batchBusy === "conf" ? "Atualizando…" : "Aplicar"}</Button>
          </>
        }
      >
        <p className="mb-3 text-sm text-slate-500">A alteração será feita documento a documento e continuará sujeita às regras de cofre do backend.</p>
        <select value={batchConf} onChange={(event) => setBatchConf(event.target.value)} className="input w-full">
          {(policy?.confidentiality || ["normal", "interno", "restrito", "confidencial", "segredo_justica"])
            .filter((value) => roleCanUseConf(role, value))
            .map((value) => <option key={value} value={value}>{confLabel(value)}</option>)}
        </select>
      </Modal>
    </div>
  );
}
